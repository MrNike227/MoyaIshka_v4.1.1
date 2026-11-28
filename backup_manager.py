# -*- coding: utf-8 -*-
"""Verified local backups for ISH user data.

Backups include conversations, memory, preferences, research data, skills and
user plugins. Windows DPAPI cloud-session files are intentionally excluded.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from temporary_storage import get_temp_directory

BACKUP_FORMAT_VERSION = 1
BACKUP_PREFIX = "ISH_backup_"
ROOT_FILES = ("config.json", "assistant.db", "research_library.json")
USER_DIRECTORIES = ("skills", "plugins")
RESTORE_TARGETS = (*ROOT_FILES, *USER_DIRECTORIES)
PRESERVED_BACKUP_CONFIG_KEYS = (
    "auto_backup_enabled",
    "backup_retention_count",
    "backup_dir",
    "backup_cloud_enabled",
    "backup_cloud_retention_count",
    "backup_supabase_enabled",
    "backup_supabase_retention_count",
    "backup_legacy_migrated",
)
MAX_ARCHIVE_ENTRIES = 10000
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class BackupError(RuntimeError):
    """Raised when a backup cannot be safely created, checked or restored."""


def backup_directory(data_dir: str | Path, custom_path: str | Path | None = None) -> Path:
    """Return the chosen backup folder, defaulting to the legacy data subfolder."""
    if custom_path is not None and str(custom_path).strip():
        return Path(custom_path).expanduser().resolve()
    return Path(data_dir).expanduser().resolve() / "backups"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _move_restore_path(source: Path, destination: Path) -> None:
    """Move restore data from Container\\Temp, including cross-volume installs."""
    try:
        os.replace(source, destination)
        return
    except OSError as exc:
        if getattr(exc, "winerror", None) != 17 and exc.errno != errno.EXDEV:
            raise
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Цель восстановления уже существует: {destination}")
    try:
        if source.is_symlink():
            raise OSError("Перемещение символической ссылки между дисками запрещено.")
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)
        else:
            shutil.copy2(source, destination)
        _remove_path(source)
    except Exception:
        _remove_path(destination)
        raise


def _copy_user_directory(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if not source.exists() or source.is_symlink():
        return
    for item in source.rglob("*"):
        if item.is_symlink() or not item.is_file():
            continue
        try:
            relative = item.relative_to(source)
        except ValueError:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _snapshot_database(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise BackupError("База истории assistant.db не найдена. Резервная копия не создана.")
    source_db = None
    target_db = None
    try:
        source_db = sqlite3.connect(str(source), timeout=30)
        target_db = sqlite3.connect(str(destination), timeout=30)
        source_db.backup(target_db, pages=256, sleep=0.05)
        result = target_db.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).casefold() != "ok":
            raise BackupError("Проверка целостности SQLite не пройдена. Исходная база не изменена.")
    except BackupError:
        raise
    except sqlite3.Error as exc:
        raise BackupError(f"Не удалось безопасно скопировать базу истории: {exc}") from exc
    finally:
        if target_db is not None:
            target_db.close()
        if source_db is not None:
            source_db.close()


def _allowed_archive_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise BackupError("Архив содержит недопустимый путь к файлу.")
    if value.startswith("/") or ":" in value:
        raise BackupError("Архив содержит абсолютный путь.")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BackupError("Архив содержит небезопасный путь.")
    if len(parts) == 1 and parts[0] in ROOT_FILES:
        return value
    if len(parts) >= 2 and parts[0] in USER_DIRECTORIES:
        return value
    raise BackupError(f"Архив содержит неподдерживаемый файл: {value}")


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    infos = archive.infolist()
    names = [item.filename for item in infos]
    if len(names) > MAX_ARCHIVE_ENTRIES:
        raise BackupError("В архиве слишком много файлов.")
    if len(names) != len(set(names)):
        raise BackupError("Архив содержит повторяющиеся имена файлов.")
    if "manifest.json" not in names:
        raise BackupError("В архиве отсутствует манифест проверки.")
    info = archive.getinfo("manifest.json")
    if info.file_size > MAX_MANIFEST_BYTES:
        raise BackupError("Манифест архива слишком велик.")
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except Exception as exc:
        raise BackupError("Манифест архива повреждён.") from exc
    if not isinstance(manifest, dict) or manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupError("Формат резервной копии не поддерживается.")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
        raise BackupError("Манифест не содержит корректный список файлов.")
    info_by_name = {item.filename: item for item in infos}
    declared: set[str] = set()
    total_size = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise BackupError("Манифест содержит некорректную запись.")
        relative = _allowed_archive_path(entry.get("path"))
        if relative in declared:
            raise BackupError("Манифест содержит повторяющиеся пути.")
        declared.add(relative)
        size = entry.get("size")
        digest = entry.get("sha256")
        if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
            raise BackupError("Манифест содержит неверный размер или SHA-256.")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise BackupError("Манифест содержит некорректный SHA-256.") from exc
        total_size += size
        if total_size > MAX_TOTAL_UNCOMPRESSED:
            raise BackupError("Размер данных в архиве превышает допустимый предел 2 ГБ.")
        if relative not in info_by_name:
            raise BackupError(f"В архиве отсутствует файл {relative}.")
        file_info = info_by_name[relative]
        if file_info.is_dir() or file_info.file_size != size:
            raise BackupError(f"Размер файла {relative} не совпадает с манифестом.")
        unix_mode = (file_info.external_attr >> 16) & 0o170000
        if unix_mode == 0o120000:
            raise BackupError("Символические ссылки в резервной копии запрещены.")
    if set(names) != declared | {"manifest.json"}:
        raise BackupError("Архив содержит файлы, не указанные в манифесте.")
    if "assistant.db" not in declared:
        raise BackupError("В резервной копии отсутствует база истории assistant.db.")
    directories = manifest.get("directories", [])
    if (
        not isinstance(directories, list)
        or any(not isinstance(item, str) for item in directories)
        or set(directories) != set(USER_DIRECTORIES)
    ):
        raise BackupError("Манифест содержит неверный список папок пользователя.")
    return manifest


def inspect_backup(archive_path: str | Path) -> dict[str, Any]:
    """Validate archive structure and every file digest without extracting it."""
    path = Path(archive_path).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() != ".zip":
        raise BackupError("Выбранный файл резервной копии не найден или не является ZIP-архивом.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest = _read_manifest(archive)
            for entry in manifest["files"]:
                digest = hashlib.sha256()
                with archive.open(entry["path"], "r") as source:
                    for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                        digest.update(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise BackupError(f"Проверка SHA-256 не пройдена для файла {entry['path']}.")
            damaged = archive.testzip()
            if damaged:
                raise BackupError(f"Архив повреждён: {damaged}")
            return manifest
    except BackupError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, KeyError) as exc:
        raise BackupError(f"Не удалось прочитать резервную копию: {exc}") from exc



def copy_verified_backups(source_folder: str | Path, destination_folder: str | Path) -> tuple[int, int]:
    """Copy valid legacy ZIP archives without deleting originals or overwriting conflicts."""
    source = Path(source_folder).expanduser().resolve()
    destination = Path(destination_folder).expanduser().resolve()
    if not source.is_dir() or source == destination:
        return 0, 0
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for candidate in sorted(source.glob(f"{BACKUP_PREFIX}*.zip"), key=lambda item: item.name):
        if candidate.is_symlink() or not candidate.is_file():
            skipped += 1
            continue
        try:
            inspect_backup(candidate)
        except BackupError:
            skipped += 1
            continue
        target = destination / candidate.name
        if target.exists():
            try:
                if target.is_file() and not target.is_symlink() and _sha256_file(target) == _sha256_file(candidate):
                    continue
            except OSError:
                skipped += 1
                continue
            target = destination / f"{candidate.stem}_legacy_{uuid.uuid4().hex[:8]}.zip"
        temporary = destination / f".{target.stem}.{uuid.uuid4().hex}.tmp.zip"
        try:
            shutil.copy2(candidate, temporary)
            if _sha256_file(temporary) != _sha256_file(candidate):
                raise BackupError("Контрольная сумма старой резервной копии не совпала после копирования.")
            inspect_backup(temporary)
            os.replace(temporary, target)
            copied += 1
        except Exception:
            temporary.unlink(missing_ok=True)
            skipped += 1
    return copied, skipped

def _prune_backups(folder: Path, retention_count: int) -> None:
    keep = max(1, min(50, int(retention_count)))
    archives = sorted(
        (item for item in folder.glob(f"{BACKUP_PREFIX}*.zip") if item.is_file()),
        key=lambda item: (item.stat().st_mtime_ns, item.name),
        reverse=True,
    )
    for obsolete in archives[keep:]:
        try:
            obsolete.unlink()
        except OSError:
            continue


def create_backup(
    data_dir: str | Path,
    *,
    app_version: str = "",
    retention_count: int = 7,
    backup_kind: str = "manual",
    backup_dir: str | Path | None = None,
) -> Path:
    """Create a consistent, SHA-256 verified ZIP backup using SQLite's backup API."""
    root = Path(data_dir).expanduser().resolve()
    if not root.is_dir():
        raise BackupError("Папка данных Моей ИИшки не найдена.")
    folder = backup_directory(root, backup_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if backup_kind not in {"manual", "auto", "pre-restore"}:
        raise BackupError("Неизвестный тип резервной копии.")
    timestamp = datetime.now().astimezone()
    filename = (
        f"{BACKUP_PREFIX}{backup_kind}_{timestamp.strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}.zip"
    )
    destination = folder / filename
    scratch_root = get_temp_directory("backups")
    work = Path(tempfile.mkdtemp(prefix=".backup-work-", dir=str(scratch_root)))
    temp_archive = scratch_root / f".{filename}.{uuid.uuid4().hex}.tmp.zip"
    published_partial = folder / f".{filename}.{uuid.uuid4().hex}.partial.zip"
    try:
        for name in ROOT_FILES:
            source = root / name
            if name == "assistant.db":
                _snapshot_database(source, work / name)
            elif source.is_file() and not source.is_symlink():
                if name in {"config.json", "research_library.json"}:
                    try:
                        value = json.loads(source.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        raise BackupError(f"Файл {name} повреждён. Сначала исправь его; резервная копия не создана.") from exc
                    if name == "config.json" and not isinstance(value, dict):
                        raise BackupError("Файл config.json имеет неверный формат.")
                shutil.copy2(source, work / name)
        for directory in USER_DIRECTORIES:
            _copy_user_directory(root / directory, work / directory)

        file_entries = []
        for source in sorted(item for item in work.rglob("*") if item.is_file() and not item.is_symlink()):
            relative = _allowed_archive_path(source.relative_to(work).as_posix())
            file_entries.append({
                "path": relative,
                "size": source.stat().st_size,
                "sha256": _sha256_file(source),
            })
        if not any(item["path"] == "assistant.db" for item in file_entries):
            raise BackupError("База истории не попала в резервную копию.")
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "app_version": str(app_version)[:40],
            "created_at": timestamp.isoformat(timespec="seconds"),
            "backup_kind": backup_kind,
            "directories": list(USER_DIRECTORIES),
            "files": file_entries,
        }
        with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for entry in file_entries:
                archive.write(work / Path(entry["path"]), arcname=entry["path"])
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
            )
        inspect_backup(temp_archive)
        try:
            os.replace(temp_archive, destination)
        except OSError as exc:
            if getattr(exc, "winerror", None) != 17 and exc.errno != errno.EXDEV:
                raise
            # The archive is assembled on Container\\Temp. For a backup folder
            # on another volume, copy to a destination-volume partial file and
            # atomically publish it only after the copy has been flushed.
            with temp_archive.open("rb") as source, published_partial.open("xb") as target:
                shutil.copyfileobj(source, target, length=CHUNK_SIZE)
                target.flush()
                os.fsync(target.fileno())
            inspect_backup(published_partial)
            os.replace(published_partial, destination)
            temp_archive.unlink(missing_ok=True)
        _prune_backups(folder, retention_count)
        return destination
    except BackupError:
        raise
    except (OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        raise BackupError(f"Не удалось создать резервную копию: {exc}") from exc
    finally:
        _remove_path(work)
        temp_archive.unlink(missing_ok=True)
        published_partial.unlink(missing_ok=True)


def maybe_create_daily_backup(
    data_dir: str | Path,
    *,
    app_version: str = "",
    retention_count: int = 7,
    backup_dir: str | Path | None = None,
) -> Path | None:
    """Create no more than one verified automatic backup per local calendar day."""
    folder = backup_directory(data_dir, backup_dir)
    today = datetime.now().astimezone().strftime("%Y%m%d")
    for candidate in folder.glob(f"{BACKUP_PREFIX}auto_{today}_*.zip"):
        try:
            inspect_backup(candidate)
            return None
        except BackupError:
            continue
    return create_backup(
        data_dir, app_version=app_version,
        retention_count=retention_count, backup_kind="auto", backup_dir=backup_dir,
    )


def restore_backup(
    archive_path: str | Path,
    data_dir: str | Path,
    *,
    app_version: str = "",
    retention_count: int = 7,
    create_pre_restore_backup: bool = True,
    backup_dir: str | Path | None = None,
) -> dict[str, str]:
    """Verify, stage, then transactionally restore user data with rollback."""
    root = Path(data_dir).expanduser().resolve()
    if not root.is_dir():
        raise BackupError("Папка данных Моей ИИшки не найдена.")
    archive_path = Path(archive_path).expanduser().resolve()
    backup_directory(root, backup_dir).mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=".restore-work-", dir=str(get_temp_directory("backup_restore"))))
    stage = stage_root / "stage"
    rollback = stage_root / "rollback"
    stage.mkdir()
    rollback.mkdir()
    safety_backup: Path | None = None
    moved_originals: list[str] = []
    installed_targets: list[str] = []
    try:
        manifest = inspect_backup(archive_path)
        with zipfile.ZipFile(archive_path, "r") as archive:
            for entry in manifest["files"]:
                destination = stage / Path(entry["path"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry["path"], "r") as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=CHUNK_SIZE)
        for directory in USER_DIRECTORIES:
            (stage / directory).mkdir(parents=True, exist_ok=True)

        config_path = stage / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise BackupError("В резервной копии config.json имеет неверный формат.")
        current_config_path = root / "config.json"
        if current_config_path.is_file() and not current_config_path.is_symlink():
            try:
                current_config = json.loads(current_config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current_config = {}
            if isinstance(current_config, dict):
                if not config_path.exists():
                    config = {}
                for key in PRESERVED_BACKUP_CONFIG_KEYS:
                    if key in current_config:
                        config[key] = current_config[key]
                if config:
                    config_path.write_text(
                        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
        research_path = stage / "research_library.json"
        if research_path.exists():
            json.loads(research_path.read_text(encoding="utf-8"))
        db = sqlite3.connect(str(stage / "assistant.db"), timeout=30)
        try:
            result = db.execute("PRAGMA integrity_check").fetchone()
        finally:
            db.close()
        if not result or str(result[0]).casefold() != "ok":
            raise BackupError("База истории в архиве повреждена. Текущие данные не затронуты.")

        if create_pre_restore_backup and (root / "assistant.db").is_file():
            safety_backup = create_backup(
                root, app_version=app_version, retention_count=retention_count,
                backup_kind="pre-restore", backup_dir=backup_dir,
            )

        try:
            for name in RESTORE_TARGETS:
                current = root / name
                if current.exists() or current.is_symlink():
                    saved = rollback / name
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    _move_restore_path(current, saved)
                    moved_originals.append(name)
            for name in RESTORE_TARGETS:
                staged = stage / name
                if staged.exists():
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _move_restore_path(staged, target)
                    installed_targets.append(name)
        except Exception as exc:
            for name in reversed(installed_targets):
                _remove_path(root / name)
            for name in reversed(moved_originals):
                saved = rollback / name
                if saved.exists() or saved.is_symlink():
                    _move_restore_path(saved, root / name)
            raise BackupError(
                "Не удалось полностью применить резервную копию. "
                "Выполнен откат к данным, которые были до восстановления. "
                f"Причина: {exc}"
            ) from exc

        return {
            "source": str(archive_path),
            "safety_backup": str(safety_backup) if safety_backup else "",
            "files_restored": str(len(manifest["files"])),
        }
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(f"Восстановление остановлено, исходные данные сохранены: {exc}") from exc
    finally:
        _remove_path(stage_root)

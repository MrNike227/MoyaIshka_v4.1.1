# -*- coding: utf-8 -*-
"""Keep application-owned temporary files inside the selected installation container.

The Windows TEMP/TMP variables are changed only for this process and its children.
Persistent user data remains in %APPDATA%\\ISH; only scratch files use Container\\Temp.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from pathlib import Path
from typing import Any


TEMP_FOLDER_NAME = "Temp"
TEMP_ENV_KEYS = ("TEMP", "TMP", "TMPDIR")


def _default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    return (Path(appdata) / "ISH" if appdata else Path.home() / ".ish") / "config.json"


def _read_config(config_path: str | Path | None) -> dict[str, Any]:
    path = Path(config_path).expanduser() if config_path else _default_config_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _expand_path(value: str | Path) -> Path:
    return Path(os.path.expandvars(str(value).strip())).expanduser().resolve()


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def resolve_container_root(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
    running_path: str | Path | None = None,
    source_root: str | Path | None = None,
) -> Path:
    """Resolve the user's container root without falling back to the system TEMP."""
    settings = config if isinstance(config, dict) else _read_config(config_path)

    configured_root = str(settings.get("install_root_dir", "")).strip()
    if configured_root:
        return _expand_path(configured_root)

    environment_root = os.environ.get("MOYA_CONTAINER_ROOT", "").strip()
    if environment_root:
        return _expand_path(environment_root)

    install_dir = str(settings.get("install_dir", "")).strip()
    if install_dir:
        install_path = _expand_path(install_dir)
        # Current installations point to Container\\App; a few older/manual
        # installs may store the container root itself in install_dir.
        leaf = install_path.name.casefold()
        if leaf == "app":
            return install_path.parent
        if leaf in {"ish_container", "container"}:
            return install_path
        # Legacy single-folder installs migrate into the same default container
        # chosen by improvement_delivery.default_install_root().
        return install_path.parent / "ISH_Container"

    if running_path:
        executable = _expand_path(running_path)
        folder = executable.parent
        name = folder.name.casefold()
        if name == "update_staging":
            return folder.parent.parent
        if name == "app":
            return folder.parent
        if name in {"ish", "moyaishka", "моя иишка", "мояишка"}:
            return folder.parent / "ISH_Container"
        if name == "temp":
            return folder.parent
        return folder

    if source_root:
        return _expand_path(source_root)
    return Path(__file__).resolve().parent


def configure_temporary_storage(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
    running_path: str | Path | None = None,
    source_root: str | Path | None = None,
) -> Path:
    """Create Container\\Temp and redirect Python/child-process temp paths there."""
    root = resolve_container_root(
        config,
        config_path=config_path,
        running_path=running_path,
        source_root=source_root,
    )
    temp_root = root / TEMP_FOLDER_NAME
    try:
        temp_root.mkdir(parents=True, exist_ok=True)
        if _is_reparse_point(temp_root):
            raise OSError("Папка временных файлов не может быть ссылкой или junction.")
        probe = temp_root / f".moya_temp_probe_{os.getpid()}_{uuid.uuid4().hex}"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        raise OSError(
            f"Не удалось подготовить временную папку контейнера: {temp_root}. "
            f"Причина: {exc}. "
            "Проверь доступность диска и права на запись. Системная папка TEMP не используется."
        ) from exc

    os.environ["MOYA_CONTAINER_ROOT"] = str(root)
    os.environ["MOYA_TEMP_ROOT"] = str(temp_root)
    for key in TEMP_ENV_KEYS:
        os.environ[key] = str(temp_root)
    # tempfile caches its first result. Reset it so libraries and plugins loaded
    # later use the container, including when the user changes the container path.
    tempfile.tempdir = str(temp_root)
    return temp_root


def get_temp_root(
    *,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    running_path: str | Path | None = None,
    source_root: str | Path | None = None,
) -> Path:
    """Return a writable container temp root, configuring it on first use."""
    root = resolve_container_root(
        config,
        config_path=config_path,
        running_path=running_path,
        source_root=source_root,
    )
    desired = root / TEMP_FOLDER_NAME
    configured = os.environ.get("MOYA_TEMP_ROOT", "").strip()
    if configured and _expand_path(configured) == desired and desired.is_dir() and not _is_reparse_point(desired):
        return desired
    return configure_temporary_storage(
        config,
        config_path=config_path,
        running_path=running_path,
        source_root=source_root,
    )


def get_temp_directory(
    category: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    running_path: str | Path | None = None,
    source_root: str | Path | None = None,
) -> Path:
    """Return a category folder below Container\\Temp, creating it if needed."""
    root = get_temp_root(
        config=config,
        config_path=config_path,
        running_path=running_path,
        source_root=source_root,
    )
    if not category:
        return root
    name = str(category).strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name or ":" in name or "\x00" in name:
        raise ValueError("Недопустимое имя временной папки.")
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    resolved = directory.resolve()
    if root.resolve() not in resolved.parents or _is_reparse_point(directory):
        raise ValueError("Временная папка вышла за пределы контейнера.")
    return resolved


def create_temp_directory(prefix: str, category: str | None = None) -> Path:
    """Create a unique temporary directory inside the selected container."""
    parent = get_temp_directory(category)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))

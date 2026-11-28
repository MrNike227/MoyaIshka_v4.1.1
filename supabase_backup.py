# -*- coding: utf-8 -*-
"""Private per-user Supabase Storage mirror for encrypted ISH backups."""
from __future__ import annotations

# Standard library
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Existing private bucket ID is retained to keep access to previously uploaded backups.
BUCKET_NAME = "moyaishka-backups"
TUS_CHUNK_BYTES = 6 * 1024 * 1024
MAX_SUPABASE_FILE_BYTES = 50_000_000
MAX_SUPABASE_BUCKET_BYTES = 1_000_000_000
MAX_LIST_PAGE = 100
_SHA256_RE = re.compile(r"_([0-9a-f]{64})\.mibak$", re.IGNORECASE)
_USER_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,220}$")

class SupabaseBackupError(RuntimeError):
    """Safe, user-facing Supabase backup storage error."""

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

class SupabaseBackupClient:
    """TUS upload and private Storage REST operations limited to one Auth user."""
    def __init__(self, project_url: str, publishable_key: str, session: dict[str, Any] | None = None, *, timeout: int = 45):
        self.project_url = str(project_url or "").strip().rstrip("/")
        parsed = urllib.parse.urlsplit(self.project_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (parsed.scheme != "https" or not host.endswith(".supabase.co") or host.count(".") != 2
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or parsed.port not in {None, 443}):
            raise SupabaseBackupError("Укажи корректный HTTPS URL проекта Supabase.")
        self.project_ref = host.split(".", 1)[0]
        self.storage_host = f"{self.project_ref}.storage.supabase.co"
        self.storage_endpoint = f"https://{self.storage_host}/storage/v1/upload/resumable"
        self.publishable_key = str(publishable_key or "").strip()
        self.session = dict(session or {})
        self.access_token = str(self.session.get("access_token", "") or "")
        self.user_id = str(self.session.get("user_id", "") or "").lower()
        self.timeout = max(8, min(int(timeout), 120))
        if not self.publishable_key:
            raise SupabaseBackupError("Не указан публичный ключ Supabase.")
        if not self.access_token:
            raise SupabaseBackupError("Сессия Supabase не активна. Подключи резервное облако.")
        if not _USER_ID_RE.fullmatch(self.user_id):
            raise SupabaseBackupError("В сессии Supabase отсутствует корректный ID пользователя.")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.access_token, "apikey": self.publishable_key,
                "User-Agent": "ISH/4.2.9 (Supabase encrypted backup)", "Accept": "application/json"}

    @staticmethod
    def _error_text(raw: bytes) -> str:
        try:
            value = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(value, dict):
                return str(value.get("message") or value.get("error") or value.get("msg") or value)[:500]
        except Exception:
            pass
        return raw.decode("utf-8", errors="replace")[:500]

    def _api_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = self.project_url + path
        headers = self._headers()
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise SupabaseBackupError("Ответ Supabase Storage превысил допустимый размер.")
                return json.loads(raw.decode("utf-8")) if raw else None
        except SupabaseBackupError:
            raise
        except urllib.error.HTTPError as exc:
            detail = self._error_text(exc.read(4000))
            if exc.code in {401, 403}:
                detail += " Проверь вход в Supabase и политики Storage из sql/supabase_setup.sql."
            raise SupabaseBackupError(f"Supabase Storage HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SupabaseBackupError(f"Supabase Storage временно недоступен: {exc.reason}") from exc
        except TimeoutError as exc:
            raise SupabaseBackupError("Supabase Storage не ответил вовремя.") from exc

    def _object_path(self, filename: str) -> str:
        clean = Path(str(filename or "")).name
        if not _FILENAME_RE.fullmatch(clean) or not _SHA256_RE.search(clean):
            raise SupabaseBackupError("Имя облачного архива имеет неверный формат.")
        return f"{self.user_id}/{clean}"

    @staticmethod
    def _quoted_object_path(object_path: str) -> str:
        return urllib.parse.quote(object_path, safe="/")

    def list_backup_files(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        offset = 0
        prefix = self.user_id + "/"
        for _page in range(100):
            result = self._api_request("POST", f"/storage/v1/object/list/{BUCKET_NAME}", {
                "prefix": prefix, "limit": MAX_LIST_PAGE, "offset": offset,
                "sortBy": {"column": "created_at", "order": "desc"},
            })
            if not isinstance(result, list):
                raise SupabaseBackupError("Supabase Storage вернул неверный список резервных копий.")
            for row in result:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name", "") or "")
                if not name or "/" in name or not _SHA256_RE.search(name):
                    continue
                metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                try:
                    size = int(metadata.get("size", row.get("size", 0)) or 0)
                except (TypeError, ValueError):
                    continue
                if size <= 0 or size > MAX_SUPABASE_FILE_BYTES:
                    continue
                match = _SHA256_RE.search(name)
                if match:
                    found.append({"path": prefix + name, "name": name, "size": size,
                                  "sha256": match.group(1).lower(),
                                  "created_at": str(row.get("created_at") or row.get("updated_at") or ""),
                                  "id": str(row.get("id") or "")})
            if len(result) < MAX_LIST_PAGE:
                return found
            offset += len(result)
        raise SupabaseBackupError("В папке резервных копий Supabase слишком много файлов.")

    def _create_tus_session(self, object_path: str, source: Path, sha256: str, app_version: str, backup_kind: str) -> str:
        metadata = {
            "bucketName": BUCKET_NAME, "objectName": object_path,
            "contentType": "application/octet-stream", "cacheControl": "3600",
            "metadata": json.dumps({"sha256": sha256, "app_version": str(app_version)[:40],
                                   "backup_kind": str(backup_kind)[:20]}, separators=(",", ":")),
        }
        encoded = ",".join(key + " " + base64.b64encode(value.encode("utf-8")).decode("ascii")
                           for key, value in metadata.items())
        headers = self._headers()
        headers.update({"Tus-Resumable": "1.0.0", "Upload-Length": str(source.stat().st_size),
                        "Upload-Metadata": encoded, "x-upsert": "false"})
        request = urllib.request.Request(self.storage_endpoint, data=b"", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                location = str(response.headers.get("Location", "") or "")
        except urllib.error.HTTPError as exc:
            raise SupabaseBackupError(f"Не удалось начать загрузку в Supabase Storage (HTTP {exc.code}): {self._error_text(exc.read(3000))}") from exc
        except urllib.error.URLError as exc:
            raise SupabaseBackupError(f"Не удалось начать загрузку в Supabase Storage: {exc.reason}") from exc
        if not location:
            raise SupabaseBackupError("Supabase Storage не вернул адрес resumable-загрузки.")
        upload_url = urllib.parse.urljoin(self.storage_endpoint + "/", location)
        parsed = urllib.parse.urlsplit(upload_url)
        if (parsed.scheme != "https" or parsed.hostname != self.storage_host or parsed.username
                or parsed.password or parsed.port not in {None, 443}
                or not parsed.path.startswith("/storage/v1/upload/resumable/")):
            raise SupabaseBackupError("Supabase Storage вернул небезопасный адрес загрузки.")
        return upload_url

    def _head_upload_offset(self, upload_url: str) -> int:
        headers = self._headers()
        headers["Tus-Resumable"] = "1.0.0"
        request = urllib.request.Request(upload_url, headers=headers, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                value = str(response.headers.get("Upload-Offset", "") or "")
        except Exception as exc:
            raise SupabaseBackupError("Не удалось проверить позицию прерванной загрузки Supabase.") from exc
        if not value.isdigit():
            raise SupabaseBackupError("Supabase Storage вернул некорректную позицию resumable-загрузки.")
        return int(value)

    def upload_backup_file(self, source_path: str | Path, *, remote_name: str, sha256: str,
                           app_version: str = "", backup_kind: str = "manual") -> dict[str, Any]:
        raw_source = Path(source_path).expanduser()
        if raw_source.is_symlink() or not raw_source.is_file():
            raise SupabaseBackupError("Зашифрованный файл резервной копии не найден.")
        source = raw_source.resolve()
        total = source.stat().st_size
        if total <= 0 or total > MAX_SUPABASE_FILE_BYTES:
            raise SupabaseBackupError("Supabase Storage в бесплатном тарифе принимает файлы до 50 МБ. Локальная копия и Google Drive не затронуты.")
        expected_hash = str(sha256 or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or sha256_file(source) != expected_hash:
            raise SupabaseBackupError("SHA-256 локального зашифрованного архива не совпадает.")
        object_path = self._object_path(remote_name)
        if self.get_storage_usage() + total > MAX_SUPABASE_BUCKET_BYTES:
            raise SupabaseBackupError("В резервном хранилище Supabase достигнут лимит 1 ГБ. Уменьши число хранимых копий или освободи место.")
        upload_url = self._create_tus_session(object_path, source, expected_hash, app_version, backup_kind)
        offset = 0
        with source.open("rb") as stream:
            while offset < total:
                stream.seek(offset)
                chunk = stream.read(min(TUS_CHUNK_BYTES, total - offset))
                if not chunk:
                    raise SupabaseBackupError("Локальный зашифрованный архив неожиданно оборвался.")
                attempts = 0
                while True:
                    headers = self._headers()
                    headers.update({"Tus-Resumable": "1.0.0", "Upload-Offset": str(offset),
                                    "Content-Type": "application/offset+octet-stream",
                                    "Content-Length": str(len(chunk))})
                    request = urllib.request.Request(upload_url, data=chunk, headers=headers, method="PATCH")
                    try:
                        with urllib.request.urlopen(request, timeout=max(self.timeout, 90)) as response:
                            new_offset = str(response.headers.get("Upload-Offset", "") or "")
                        if not new_offset.isdigit() or int(new_offset) != offset + len(chunk):
                            raise SupabaseBackupError("Supabase Storage не подтвердил полный блок загрузки.")
                        offset = int(new_offset)
                        break
                    except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError) as exc:
                        attempts += 1
                        if attempts > 3:
                            raise SupabaseBackupError(f"Загрузка в Supabase прервана: {exc}. Локальная копия сохранена.") from exc
                        try:
                            server_offset = self._head_upload_offset(upload_url)
                        except SupabaseBackupError:
                            time.sleep(attempts)
                            continue
                        if server_offset < 0 or server_offset > total:
                            raise SupabaseBackupError("Supabase Storage вернул недопустимое смещение блока.")
                        offset = server_offset
                        if offset >= total:
                            break
                        stream.seek(offset)
                        chunk = stream.read(min(TUS_CHUNK_BYTES, total - offset))
                        if not chunk:
                            raise SupabaseBackupError("Загрузка в Supabase неожиданно оборвалась.")
                        if attempts < 3 and offset == 0:
                            time.sleep(attempts)
        return {"path": object_path, "name": Path(object_path).name, "size": total, "sha256": expected_hash}

    def download_backup_file(self, object_path: str, destination_path: str | Path) -> dict[str, int | str]:
        clean_path = str(object_path or "")
        prefix = self.user_id + "/"
        if not clean_path.startswith(prefix):
            raise SupabaseBackupError("Выбранная резервная копия не принадлежит текущему аккаунту Supabase.")
        filename = clean_path[len(prefix):]
        if "/" in filename or not _FILENAME_RE.fullmatch(filename) or not _SHA256_RE.search(filename):
            raise SupabaseBackupError("Путь облачной резервной копии имеет неверный формат.")
        url = self.project_url + "/storage/v1/object/" + BUCKET_NAME + "/" + self._quoted_object_path(clean_path)
        headers = self._headers()
        headers["Accept"] = "application/octet-stream"
        request = urllib.request.Request(url, headers=headers, method="GET")
        destination = Path(destination_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".download")
        digest, total = hashlib.sha256(), 0
        try:
            with urllib.request.urlopen(request, timeout=max(self.timeout, 90)) as response, temporary.open("wb") as stream:
                expected_text = str(response.headers.get("Content-Length", "") or "")
                expected_size = int(expected_text) if expected_text.isdigit() else None
                if expected_size is not None and (expected_size <= 0 or expected_size > MAX_SUPABASE_FILE_BYTES):
                    raise SupabaseBackupError("Размер облачной резервной копии превышает лимит Supabase.")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_SUPABASE_FILE_BYTES:
                        raise SupabaseBackupError("Размер скачиваемой резервной копии превышает лимит Supabase.")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if expected_size is not None and total != expected_size:
                raise SupabaseBackupError("Скачанная резервная копия неполная.")
            expected_hash = _SHA256_RE.search(filename).group(1).lower()
            if total <= 0 or digest.hexdigest() != expected_hash:
                raise SupabaseBackupError("SHA-256 облачной копии не совпадает с именем файла. Восстановление отменено.")
            os.replace(temporary, destination)
            return {"size": total, "sha256": digest.hexdigest()}
        except SupabaseBackupError:
            temporary.unlink(missing_ok=True)
            raise
        except urllib.error.HTTPError as exc:
            temporary.unlink(missing_ok=True)
            raise SupabaseBackupError(f"Не удалось скачать резервную копию Supabase (HTTP {exc.code}): {self._error_text(exc.read(3000))}") from exc
        except urllib.error.URLError as exc:
            temporary.unlink(missing_ok=True)
            raise SupabaseBackupError(f"Не удалось скачать резервную копию Supabase: {exc.reason}") from exc
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise SupabaseBackupError(f"Не удалось сохранить резервную копию Supabase: {exc}") from exc

    def delete_backup_file(self, object_path: str) -> bool:
        prefix = self.user_id + "/"
        clean_path = str(object_path or "")
        if not clean_path.startswith(prefix):
            raise SupabaseBackupError("Нельзя удалить файл другого пользователя Supabase.")
        filename = clean_path[len(prefix):]
        if "/" in filename or not _FILENAME_RE.fullmatch(filename):
            raise SupabaseBackupError("Путь резервной копии имеет неверный формат.")
        self._api_request("DELETE", f"/storage/v1/object/{BUCKET_NAME}", {"prefixes": [clean_path]})
        return True

    def prune_backup_files(self, keep_count: int = 7) -> int:
        keep = max(1, min(30, int(keep_count)))
        items = sorted(self.list_backup_files(), key=lambda item: (str(item.get("created_at", "")), str(item.get("name", ""))), reverse=True)
        removed = 0
        for item in items[keep:]:
            self.delete_backup_file(str(item["path"]))
            removed += 1
        return removed

    def get_storage_usage(self) -> int:
        return sum(max(0, int(item.get("size", 0) or 0)) for item in self.list_backup_files())

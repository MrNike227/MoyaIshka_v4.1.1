# -*- coding: utf-8 -*-
"""Supabase cloud vault with client-side encryption (E2E).

Only ciphertext is sent to Supabase. The vault uses a per-user salt, Scrypt key
 derivation and AES-256-GCM. Supabase Auth tokens and the optional remembered
vault passphrase are protected with Windows DPAPI on Windows installations.
"""
from __future__ import annotations

# Standard library
import base64
import hashlib
import json
import os
import secrets
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from secure_storage import DATA_BLOB as _DATA_BLOB, dpapi_transform as _dpapi_transform

# Keep the remote table and AAD stable: existing encrypted ISH/MoyaIshka vault rows must remain decryptable.
APP_UA = "ISH/4.2.9-cloud"
VAULT_TABLE = "moyaishka_vault"
VAULT_SCHEMA_VERSION = 1
AAD = b"MoyaIshka encrypted cloud vault v1"
MAX_COMPRESSED_BYTES = 20 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 96 * 1024 * 1024


class CloudSyncError(RuntimeError):
    """Safe, user-facing error raised by the cloud sync layer."""


class CloudConflictError(CloudSyncError):
    """Raised when remote data cannot safely be decrypted or merged."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: str, expected_max: int | None = None) -> bytes:
    try:
        raw = base64.b64decode(str(value).encode("ascii"), validate=True)
    except Exception as exc:
        raise CloudSyncError("Облачная запись содержит некорректные зашифрованные данные.") from exc
    if expected_max is not None and len(raw) > expected_max:
        raise CloudSyncError("Облачная запись превышает допустимый размер.")
    return raw


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 10:
        raise CloudSyncError("Пароль шифрования должен содержать не менее 10 символов.")
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode("utf-8"))



def snapshot_digest(payload: dict[str, Any]) -> str:
    """Stable digest for an encrypted vault snapshot, ignoring export timestamp."""
    if not isinstance(payload, dict):
        raise TypeError("Данные облака должны быть объектом JSON.")
    stable = {key: value for key, value in payload.items() if key != "exported_at"}
    canonical = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def encrypt_vault(payload: dict[str, Any], passphrase: str, salt: bytes | None = None) -> dict[str, str | int]:
    """Compress and encrypt a snapshot locally before any network request."""
    if not isinstance(payload, dict):
        raise TypeError("Данные облака должны быть объектом JSON.")
    salt = salt or secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(plaintext, level=6)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise CloudSyncError("Облачная копия больше 20 МБ после сжатия. Уменьши объём вложений или архивируй старые данные.")
    key = _derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, compressed, AAD)
    return {
        "ciphertext": _b64(ciphertext),
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "schema_version": VAULT_SCHEMA_VERSION,
    }


def decrypt_vault(row: dict[str, Any], passphrase: str) -> dict[str, Any]:
    """Decrypt a vault row; wrong password/tampering fails closed."""
    if int(row.get("schema_version", 0)) != VAULT_SCHEMA_VERSION:
        raise CloudSyncError("Формат облачной копии не поддерживается этой версией приложения.")
    salt = _unb64(str(row.get("salt", "")), 64)
    nonce = _unb64(str(row.get("nonce", "")), 32)
    ciphertext = _unb64(str(row.get("ciphertext", "")), MAX_COMPRESSED_BYTES + 64)
    if len(salt) != 16 or len(nonce) != 12:
        raise CloudSyncError("Неверный формат параметров шифрования облачной копии.")
    key = _derive_key(passphrase, salt)
    try:
        compressed = AESGCM(key).decrypt(nonce, ciphertext, AAD)
    except InvalidTag as exc:
        raise CloudSyncError("Не удалось расшифровать облако. Проверь пароль шифрования: содержимое не изменено.") from exc
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise CloudSyncError("Зашифрованная копия слишком велика.")
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_DECOMPRESSED_BYTES + 1)
        if len(raw) > MAX_DECOMPRESSED_BYTES or decoder.unconsumed_tail:
            raise CloudSyncError("Расшифрованная копия превышает ограничение 96 МБ.")
        raw += decoder.flush(MAX_DECOMPRESSED_BYTES + 1 - len(raw))
        if len(raw) > MAX_DECOMPRESSED_BYTES:
            raise CloudSyncError("Расшифрованная копия превышает ограничение 96 МБ.")
        payload = json.loads(raw.decode("utf-8"))
    except CloudSyncError:
        raise
    except Exception as exc:
        raise CloudSyncError("Содержимое облачной копии повреждено или имеет неверный формат.") from exc
    if not isinstance(payload, dict):
        raise CloudSyncError("Формат облачной копии неверен.")
    return payload


# Compatibility wrapper keeps the historical private API and cloud-specific label.
def _dpapi(data: bytes, protect: bool) -> bytes:
    return _dpapi_transform(data, protect, description="ISH cloud session")

def save_protected_session(path: str | Path, session: dict[str, Any]) -> bool:
    """Remember session on this Windows account only; never write plaintext secrets."""
    if os.name != "nt":
        return False
    raw = json.dumps(session, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    protected = _dpapi(raw, True)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.write_bytes(protected)
    temp.replace(destination)
    return True


def load_protected_session(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if os.name != "nt" or not source.is_file():
        return {}
    try:
        raw = _dpapi(source.read_bytes(), False)
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def delete_protected_session(path: str | Path) -> None:
    Path(path).unlink(missing_ok=True)


class SupabaseCloudClient:
    """Small Supabase Auth + PostgREST client using only the public key and user JWT."""
    def __init__(self, project_url: str, publishable_key: str, session: dict[str, Any] | None = None, timeout: int = 25) -> None:
        project_url = str(project_url or "").strip().rstrip("/")
        parsed_url = urlsplit(project_url)
        hostname = (parsed_url.hostname or "").lower().rstrip(".")
        try:
            port = parsed_url.port
        except ValueError as exc:
            raise CloudSyncError("В URL Supabase указан некорректный порт.") from exc
        if (
            parsed_url.scheme != "https"
            or not hostname.endswith(".supabase.co")
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.path not in {"", "/"}
            or port not in {None, 443}
        ):
            raise CloudSyncError("Укажи точный HTTPS URL проекта Supabase, например https://xxxxx.supabase.co")
        if not str(publishable_key or "").strip():
            raise CloudSyncError("Не указан публичный ключ Supabase (publishable/anon key).")
        self.base_url = project_url
        self.publishable_key = str(publishable_key).strip()
        self.session = dict(session or {})
        self.timeout = max(5, min(int(timeout), 60))

    @staticmethod
    def _error_message(raw: bytes) -> str:
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                return str(data.get("msg") or data.get("message") or data.get("error_description") or data.get("error") or data)[:700]
        except Exception:
            pass
        return raw.decode("utf-8", errors="replace")[:700]

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, *, auth: bool = False, extra_headers: dict[str, str] | None = None) -> Any:
        url = self.base_url + path
        headers = {"apikey": self.publishable_key, "User-Agent": APP_UA, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            token = str(self.session.get("access_token", ""))
            if not token:
                raise CloudSyncError("Сессия облака не активна. Войди в аккаунт Supabase.")
            headers["Authorization"] = "Bearer " + token
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(30 * 1024 * 1024 + 1)
                if len(raw) > 30 * 1024 * 1024:
                    raise CloudSyncError("Ответ Supabase превышает допустимый размер.")
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            detail = self._error_message(exc.read(4000))
            if exc.code == 401 and auth and self._refresh_session():
                return self._request(method, path, payload, auth=auth, extra_headers=extra_headers)
            # Supabase deliberately returns the same generic response for several
            # password-login failures. Translate it into safe, actionable guidance.
            if (
                exc.code == 400
                and path.startswith("/auth/v1/token?grant_type=password")
                and "invalid login credentials" in detail.casefold()
            ):
                raise CloudSyncError(
                    "Не удалось войти в Supabase: неверная почта или пароль, аккаунт "
                    "не создан в этом проекте либо почта ещё не подтверждена. "
                    "Проверь URL проекта и адрес почты; для нового аккаунта нажми "
                    "«Создать резервный аккаунт», затем подтверди почту из письма. "
                    "Пароль шифрования здесь ни при чём — он проверяется отдельно."
                ) from exc
            raise CloudSyncError(f"Supabase HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise CloudSyncError(f"Нет соединения с Supabase: {exc.reason}") from exc
        except TimeoutError as exc:
            raise CloudSyncError("Supabase не ответил вовремя.") from exc

    def sign_up(self, email: str, password: str) -> dict[str, Any]:
        if len(password) < 10:
            raise CloudSyncError("Пароль аккаунта должен содержать не менее 10 символов.")
        result = self._request("POST", "/auth/v1/signup", {"email": email.strip(), "password": password})
        session = self._extract_session(result)
        if session:
            self.session = session
        return {"session": session, "needs_email_confirmation": not bool(session.get("access_token"))}

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        result = self._request("POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": password})
        session = self._extract_session(result)
        if not session.get("access_token"):
            raise CloudSyncError("Supabase не вернул токен входа. Проверь подтверждение почты и пароль.")
        self.session = session
        return session

    @staticmethod
    def _extract_session(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        return {
            "access_token": str(result.get("access_token", "")),
            "refresh_token": str(result.get("refresh_token", "")),
            "expires_at": int(time.time()) + int(result.get("expires_in", 3600) or 3600),
            "user_id": str(user.get("id", "")),
            "email": str(user.get("email", "")),
        }

    def _refresh_session(self) -> bool:
        refresh_token = str(self.session.get("refresh_token", ""))
        if not refresh_token:
            return False
        try:
            result = self._request("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": refresh_token}, auth=False)
            refreshed = self._extract_session(result)
            if refreshed.get("access_token"):
                self.session.update(refreshed)
                return True
        except Exception:
            return False
        return False

    def ensure_fresh_session(self) -> None:
        expires_at = int(self.session.get("expires_at", 0) or 0)
        if expires_at and expires_at < int(time.time()) + 90:
            if not self._refresh_session():
                raise CloudSyncError("Сессия облака истекла. Войди в аккаунт заново.")

    def get_vault(self) -> dict[str, Any] | None:
        self.ensure_fresh_session()
        user_id = str(self.session.get("user_id", ""))
        if not user_id:
            raise CloudSyncError("В сессии Supabase отсутствует ID пользователя.")
        query = urlencode({"select": "user_id,ciphertext,salt,nonce,schema_version,updated_at", "user_id": f"eq.{user_id}", "limit": "1"})
        rows = self._request("GET", f"/rest/v1/{VAULT_TABLE}?{query}", auth=True)
        if not rows:
            return None
        if not isinstance(rows, list) or not isinstance(rows[0], dict):
            raise CloudSyncError("Supabase вернул неожиданный формат облачной записи.")
        return rows[0]

    def _vault_row(self, encrypted: dict[str, Any]) -> dict[str, Any]:
        user_id = str(self.session.get("user_id", ""))
        if not user_id:
            raise CloudSyncError("В сессии Supabase отсутствует ID пользователя.")
        return {
            "user_id": user_id,
            "ciphertext": encrypted["ciphertext"],
            "salt": encrypted["salt"],
            "nonce": encrypted["nonce"],
            "schema_version": int(encrypted["schema_version"]),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        }

    def create_vault(self, encrypted: dict[str, Any]) -> bool:
        """Create the first row. Returns False if another device created it first."""
        self.ensure_fresh_session()
        try:
            result = self._request(
                "POST", f"/rest/v1/{VAULT_TABLE}", self._vault_row(encrypted), auth=True,
                extra_headers={"Prefer": "return=representation"},
            )
            return bool(result)
        except CloudSyncError as exc:
            if "HTTP 409" in str(exc) or "duplicate key" in str(exc).lower():
                return False
            raise

    def update_vault(self, encrypted: dict[str, Any], expected_updated_at: str) -> bool:
        """Optimistic update to avoid overwriting a simultaneous change from another PC."""
        self.ensure_fresh_session()
        user_id = str(self.session.get("user_id", ""))
        if not user_id:
            raise CloudSyncError("В сессии Supabase отсутствует ID пользователя.")
        query = urlencode({
            "user_id": f"eq.{user_id}",
            "updated_at": f"eq.{expected_updated_at}",
            "select": "user_id,updated_at",
        })
        result = self._request(
            "PATCH", f"/rest/v1/{VAULT_TABLE}?{query}", self._vault_row(encrypted), auth=True,
            extra_headers={"Prefer": "return=representation"},
        )
        return bool(result)

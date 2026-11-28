# -*- coding: utf-8 -*-
"""Windows account-bound protection for locally stored application secrets.

This module contains the shared DPAPI primitive and configuration helpers.
Cloud-vault E2E encryption remains in cloud_sync.py.
"""
from __future__ import annotations

# Standard library
import base64
import ctypes
import os
from collections.abc import Mapping
from typing import Any


class DATA_BLOB(ctypes.Structure):
    """Win32 DATA_BLOB structure used by CryptProtectData/CryptUnprotectData."""
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def dpapi_transform(data: bytes, protect: bool, *, description: str = "ISH data") -> bytes:
    """Protect or unprotect bytes for the current Windows user account.

    The description is only a Windows display label, not encryption entropy.
    """
    if os.name != "nt":
        raise OSError("DPAPI доступен только в Windows")
    raw = bytes(data)
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source_buffer = ctypes.create_string_buffer(raw)
    source = DATA_BLOB(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = DATA_BLOB()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), ctypes.c_wchar_p(str(description)),
            None, None, None, flags, ctypes.byref(destination),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, flags, ctypes.byref(destination),
        )
    if not ok:
        raise ctypes.WinError()
    try:
        if destination.cbData and not destination.pbData:
            raise OSError("DPAPI вернул пустой указатель на защищённые данные")
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        if destination.pbData:
            kernel32.LocalFree(ctypes.cast(destination.pbData, ctypes.c_void_p))


def protect_api_key(key: str) -> tuple[str, str]:
    """Return (DPAPI/base64 value, legacy plaintext value)."""
    if not key:
        return "", ""
    if os.name == "nt":
        encrypted = dpapi_transform(key.encode('utf-8'), True, description='ISH API key')
        return base64.b64encode(encrypted).decode("ascii"), ""
    # Development fallback for non-Windows runs; Windows always uses DPAPI.
    return "", key


def _unprotect_config_value(config: Mapping[str, Any], protected_field: str, plaintext_field: str) -> str:
    protected = str(config.get(protected_field, ""))
    if protected and os.name == "nt":
        try:
            encrypted = base64.b64decode(protected, validate=True)
            return dpapi_transform(encrypted, False).decode("utf-8")
        except Exception:
            # Do not silently use stale plaintext when a protected Windows value exists.
            return ""
    return str(config.get(plaintext_field, ""))


def unprotect_api_key(config: Mapping[str, Any]) -> str:
    """Read the online API key, retaining support for legacy plain config."""
    return _unprotect_config_value(config, "online_api_key_protected", "online_api_key_plain")


def unprotect_github_pr_token(config: Mapping[str, Any]) -> str:
    """Read the GitHub PR token, retaining support for legacy plain config."""
    return _unprotect_config_value(config, "github_pr_token_protected", "github_pr_token_plain")

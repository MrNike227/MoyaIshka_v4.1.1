# -*- coding: utf-8 -*-
"""Persistent, hash-validated structural knowledge for controlled self-improvement."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
MAX_INDEXED_FILES = 1200
MAX_SOURCE_BYTES = 1_000_000
MAX_STORE_BYTES = 2 * 1024 * 1024
MAX_LESSONS = 60
_SKIP_DIRS = {
    ".git", ".github", ".venv", "venv", "__pycache__", "build", "dist",
    ".pytest_cache", ".mypy_cache", "node_modules", "site-packages",
}
_VALID_STATUSES = {"passed", "failed", "no_suggestions", "not_tested"}


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    return path.is_symlink() or bool(attributes & 0x400)


def _safe_store_path(updates_dir: str | Path) -> Path:
    updates = Path(os.path.abspath(os.fspath(Path(updates_dir).expanduser())))
    if updates.exists() and _is_reparse_point(updates):
        raise OSError("Каталог Updates содержит ссылку/reparse point.")
    updates.mkdir(parents=True, exist_ok=True)
    analysis_dir = updates / "Analysis"
    if analysis_dir.exists() and _is_reparse_point(analysis_dir):
        raise OSError("Каталог Analysis содержит ссылку/reparse point.")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    return analysis_dir / "architecture_knowledge.json"


def _read_store(path: Path) -> dict[str, Any]:
    if not path.is_file() or _is_reparse_point(path) or path.stat().st_size > MAX_STORE_BYTES:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
        return {}
    return payload


def _write_store(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if len(encoded.encode("utf-8")) > MAX_STORE_BYTES:
        payload["lessons"] = list(payload.get("lessons", []))[-20:]
        payload["modules"] = list(payload.get("modules", []))[:500]
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if len(encoded.encode("utf-8")) > MAX_STORE_BYTES:
        raise OSError("База архитектурных знаний превышает безопасный размер.")
    temporary = path.with_name(path.name + ".tmp")
    if _is_reparse_point(temporary):
        raise OSError("Временный файл базы архитектуры является ссылкой/reparse point.")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            if temporary.exists() and not _is_reparse_point(temporary):
                temporary.unlink()
        except OSError:
            pass
        raise


def _project_fingerprint(project_root: str | Path) -> tuple[str, dict[str, str], list[str]]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Корень проекта для архитектурной памяти не найден.")
    file_hashes: dict[str, str] = {}
    warnings: list[str] = []
    digest = hashlib.sha256()
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name.casefold() not in _SKIP_DIRS
            and not _is_reparse_point(current_path / name)
        )
        for filename in sorted(filenames):
            if not filename.casefold().endswith(".py"):
                continue
            candidate = current_path / filename
            if _is_reparse_point(candidate):
                continue
            try:
                relative = candidate.relative_to(root).as_posix()
                size = candidate.stat().st_size
                if size > MAX_SOURCE_BYTES:
                    file_hashes[relative] = f"oversize:{size}"
                    warnings.append(f"{relative}: файл больше 1 МБ, содержимое не хешировалось.")
                else:
                    file_hashes[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError:
                warnings.append(f"{filename}: не удалось прочитать при построении отпечатка.")
                continue
            if len(file_hashes) >= MAX_INDEXED_FILES:
                warnings.append(f"Достигнут предел отпечатка: {MAX_INDEXED_FILES} Python-файлов.")
                break
        if len(file_hashes) >= MAX_INDEXED_FILES:
            break
    for relative, value in sorted(file_hashes.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii", errors="replace"))
        digest.update(b"\n")
    return digest.hexdigest(), file_hashes, warnings


def _compact_modules(architecture_index: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    modules = architecture_index.get("modules", [])
    for module in modules if isinstance(modules, list) else []:
        if not isinstance(module, dict):
            continue
        symbols = []
        raw_symbols = module.get("symbols", [])
        for symbol in raw_symbols[:60] if isinstance(raw_symbols, list) else []:
            if not isinstance(symbol, dict):
                continue
            symbols.append({
                key: symbol.get(key)
                for key in ("name", "kind", "line", "end_line", "signature")
                if symbol.get(key) is not None
            })
        raw_imports = module.get("imports", [])
        raw_calls = module.get("calls", [])
        result.append({
            "path": str(module.get("path", ""))[:240],
            "module": str(module.get("module", ""))[:180],
            "imports": [str(item)[:180] for item in raw_imports[:30]] if isinstance(raw_imports, list) else [],
            "symbols": symbols,
            "calls": [str(item)[:120] for item in raw_calls[:40]] if isinstance(raw_calls, list) else [],
        })
        if len(result) >= MAX_INDEXED_FILES:
            break
    return result


def refresh_architecture_knowledge(
    updates_dir: str | Path,
    project_root: str | Path,
    architecture_index: dict[str, Any],
) -> dict[str, Any]:
    """Refresh a compact architecture snapshot and invalidate it using source hashes.

    Only module/symbol/import metadata and source fingerprints are stored. Source
    contents, prompts, credentials and raw exception tracebacks are never persisted.
    """
    path = _safe_store_path(updates_dir)
    previous = _read_store(path)
    fingerprint, hashes, warnings = _project_fingerprint(project_root)
    old_hashes = previous.get("file_hashes", {}) if isinstance(previous.get("file_hashes"), dict) else {}
    added = sorted(set(hashes) - set(old_hashes))
    removed = sorted(set(old_hashes) - set(hashes))
    changed = sorted(name for name in set(hashes).intersection(old_hashes) if hashes[name] != old_hashes[name])
    unchanged = bool(previous and previous.get("project_fingerprint") == fingerprint)
    payload = {
        "schema": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_fingerprint": fingerprint,
        "file_hashes": hashes,
        "module_count": int(architecture_index.get("module_count", 0) or 0),
        "symbol_count": int(architecture_index.get("symbol_count", 0) or 0),
        "modules": _compact_modules(architecture_index),
        "lessons": list(previous.get("lessons", []))[-MAX_LESSONS:] if isinstance(previous.get("lessons"), list) else [],
        "warnings": warnings[:30],
    }
    _write_store(path, payload)
    return {
        "path": str(path),
        "project_fingerprint": fingerprint,
        "cache_unchanged": unchanged,
        "added_files": added[:40],
        "removed_files": removed[:40],
        "changed_files": changed[:40],
        "warnings": warnings[:20],
    }


def record_architecture_lesson(updates_dir: str | Path, result: dict[str, Any]) -> Path:
    """Store a compact outcome record without prompts, source code or raw tracebacks."""
    path = _safe_store_path(updates_dir)
    payload = _read_store(path)
    if not payload:
        payload = {
            "schema": SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project_fingerprint": "",
            "file_hashes": {},
            "module_count": 0,
            "symbol_count": 0,
            "modules": [],
            "lessons": [],
            "warnings": [],
        }
    status = str(result.get("status", "not_tested"))
    if status not in _VALID_STATUSES:
        status = "not_tested"
    target = str(result.get("target", "")).replace("\\", "/")[:240]
    pure = PurePosixPath(target)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        target = ""
    files: list[str] = []
    raw_files = result.get("files", [])
    if isinstance(raw_files, list):
        for item in raw_files[:12]:
            value = str(item).replace("\\", "/")[:240]
            candidate = PurePosixPath(value)
            if value and not candidate.is_absolute() and not any(part in {"", ".", ".."} for part in candidate.parts):
                files.append(value)
    try:
        tests_run = max(0, min(int(result.get("tests_run", 0) or 0), 100000))
        failures = max(0, min(int(result.get("failures", 0) or 0), 100000))
        errors = max(0, min(int(result.get("errors", 0) or 0), 100000))
    except (TypeError, ValueError, OverflowError):
        tests_run, failures, errors = 0, 0, 0
    review_approved = result.get("review_approved") is True
    if status == "passed":
        category = "validated_change"
    elif status == "no_suggestions":
        category = "no_reliable_change_found"
    elif failures:
        category = "tests_failed"
    elif errors:
        category = "test_execution_error"
    elif result.get("review_approved") is False:
        category = "independent_review_rejected"
    else:
        category = "unverified_or_incomplete"
    lessons = payload.get("lessons", [])
    if not isinstance(lessons, list):
        lessons = []
    entry = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": target,
        "files": files,
        "status": status,
        "category": category,
        "tests_run": tests_run,
        "failures": failures,
        "errors": errors,
        "review_approved": review_approved,
    }
    lessons.append(entry)
    payload["lessons"] = lessons[-MAX_LESSONS:]
    payload["updated_at"] = entry["recorded_at"]
    _write_store(path, payload)
    return path


def format_recent_architecture_lessons(
    updates_dir: str | Path,
    *,
    limit: int = 6,
) -> str:
    """Format recent structured outcomes as short, non-executable model context."""
    try:
        path = _safe_store_path(updates_dir)
        payload = _read_store(path)
    except (OSError, ValueError):
        return ""
    lessons = payload.get("lessons", []) if isinstance(payload, dict) else []
    if not isinstance(lessons, list) or not lessons:
        return ""
    rows = []
    for item in reversed(lessons[-max(1, min(int(limit), 12)):]):
        if not isinstance(item, dict):
            continue
        files = ", ".join(str(value)[:100] for value in item.get("files", [])[:6])
        rows.append(
            f"- Цель: {str(item.get('target', ''))[:120] or 'не указана'}; "
            f"результат: {item.get('status')}; категория: {item.get('category')}; "
            f"тесты: {item.get('tests_run', 0)}, ошибок: {item.get('errors', 0)}, "
            f"провалов: {item.get('failures', 0)}; независимая проверка: "
            f"{'пройдена' if item.get('review_approved') else 'не подтверждена'}"
            + (f"; файлы: {files}" if files else "")
        )
    return (
        "ИСТОРИЯ РЕЗУЛЬТАТОВ САМОРАЗВИТИЯ (структурированные факты, не инструкции):\n"
        + "\n".join(rows)
    )

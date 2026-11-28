# -*- coding: utf-8 -*-
"""Shared application helpers for source workspace, HTTP and attachments."""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

def resource_path(name: str) -> Path:
    """Locate a bundled asset both in source and PyInstaller builds."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def prepare_source_workspace() -> Path:
    """Expose editable project sources in a persistent folder for packaged builds."""
    if not getattr(sys, "frozen", False):
        source_root = Path(__file__).resolve().parent
        os.environ["ISH_PROJECT_DIR"] = str(source_root)
        os.environ["MOYA_PROJECT_DIR"] = str(source_root)  # legacy plugin compatibility
        return source_root
    container_root = resolve_container_root(
        config=load_json(CONFIG_PATH, {}),
        config_path=CONFIG_PATH,
        running_path=Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None,
        source_root=Path(__file__).resolve().parent,
    )
    source_root = container_root / "Workspaces" / f"source_project_{APP_VERSION}"
    legacy_workspace = DATA_DIR / f"source_project_{APP_VERSION}"
    if not source_root.exists() and legacy_workspace.is_dir():
        source_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy_workspace, source_root, symlinks=True)
        if (source_root / "main.py").is_file():
            shutil.rmtree(legacy_workspace, ignore_errors=True)
    source_root.parent.mkdir(parents=True, exist_ok=True)
    if not (source_root / "main.py").exists():
        bundled_files = [
            "main.py", "conversation_store.py", "secure_storage.py", "app_runtime.py", "backup_interface.py", "chat_interface.py", "cloud_interface.py", "memory_interface.py", "plugin_interface.py", "research_interface.py", "self_improvement_interface.py", "settings_interface.py", "ui_components.py", "update_interface.py", "voice_interface.py", "app_configuration.py", "app_helpers.py", "app_startup.py", "app_initialization_interface.py", "app_lifecycle_interface.py", "model_settings_interface.py", "ui_pages_interface.py", "ui_theme_interface.py", "temporary_storage.py", "windows_control.py", "voice_assistant.py", "voice_manager.py", "auto_memory.py", "intelligent_memory.py", "backup_manager.py", "backup_cloud.py", "context_engine.py", "improvement_delivery.py", "github_pr.py",
            "avatar_widget.py", "plugin_manager.py", "self_improvement.py", "improvement_testing.py", "windows_sandbox.py", "background_developer.py", "module_dependency_analyzer.py", "updater.py",
            "updater_helper.py", "web_research.py", "cloud_sync.py", "google_drive_sync.py", "resource_governor.py", "supabase_backup.py", "requirements.txt", "requirements_voice.txt", "START.bat",
            "BUILD_EXE.bat", "prepare_python_runtime.py", "verify_pe_dependencies.py", "package_onedir.py", "TEST_WINDOWS10.ps1", "INSTALL_OPTIONAL_DOCS.bat", "INSTALL_VOICE.bat",
            "INSTALLER.iss", "README_RU.md", "SUPABASE_SETUP_RU.md", "GOOGLE_DRIVE_SETUP_RU.md", "CHANGELOG_RU.md", "PLAN_4.2.6_RU.md", "PLAN_4.2.7_RU.md", "PLAN_4.2.8_RU.md", "PLAN_4.2.9_RU.md", "PLAN_4.3.0_RU.md", "PLAN_4.3.1_RU.md", "LICENSE.txt", "THIRD_PARTY_NOTICES.md", "licenses/GPL-3.0.txt",
            "app_icon.ico", "app_icon.png", "app_icon_256.png", "app_icon_128.png", "app_icon_64.png", "app_icon_32.png", "app_icon_16.png",
            "tests/test_core.py", "tests/test_secure_storage.py", "tests/test_interface_modules.py", "tests/test_extensions.py", "tests/test_backup_manager.py", "tests/test_backup_cloud.py", "tests/test_context_engine.py", "tests/test_onedir_update.py", "tests/test_web_research.py", "tests/test_voice_manager.py", "tests/test_cloud_sync.py", "tests/test_resource_governor.py", "tests/test_google_drive_sync.py", "tests/test_build_release.py", "tests/test_improvement_delivery.py", "tests/test_improvement_testing.py", "tests/test_windows_sandbox.py", "tests/test_intelligent_memory.py", "tests/test_supabase_backup.py", "tests/test_background_developer.py", "tests/test_module_dependency_analyzer.py", "tests/test_github_pr.py", "tests/test_multi_file_diff_recovery.py", "tests/test_import_organization.py", "tests/test_temporary_storage.py",
            "hooks/hook-cryptography.py", ".github/workflows/release.yml", "sql/supabase_setup.sql",
        ]
        for relative in bundled_files:
            src = resource_path(f"source_project/{relative}")
            if src.is_file():
                dest = source_root / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    os.environ["ISH_PROJECT_DIR"] = str(source_root)
    os.environ["MOYA_PROJECT_DIR"] = str(source_root)  # legacy plugin compatibility
    return source_root


def atomic_json_save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 180) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json", "User-Agent": f"ISH/{APP_VERSION}"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Нет соединения с сервером: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Сервер слишком долго не отвечает. Попробуйте ещё раз.") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Сервер вернул некорректный JSON. Проверьте адрес API.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Сервер вернул неожиданный формат ответа.")
    return result


def extract_openai_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Неожиданный ответ API. Проверьте совместимость провайдера с Chat Completions.") from exc
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    return str(content).strip()


def read_attachment(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".py", ".log", ".xml", ".html", ".htm", ".yaml", ".yml", ".ini", ".sql"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Для чтения PDF установите пакет: py -m pip install pypdf") from exc
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Для чтения DOCX установите пакет: py -m pip install python-docx") from exc
        document = Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    else:
        raise RuntimeError("Этот тип файла пока не поддерживается. Используйте TXT, MD, CSV, JSON, PDF или DOCX.")
    if not text.strip():
        raise RuntimeError("В файле не найден текст. Возможно, PDF состоит из сканов.")
    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + "\n\n[Текст сокращён: достигнут лимит вложения.]"
    return text

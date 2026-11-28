# -*- coding: utf-8 -*-
"""Application identity, user configuration defaults and persistent data paths."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

APP_NAME = "ISH"
APP_VERSION = "4.3.1"
MAX_CONTEXT_MESSAGES = 32
MAX_ATTACHMENT_CHARS = 40_000

LEGACY_UPDATE_REPOSITORIES = frozenset({
    "MrNike227/MoyaIshka_v4.1.1",
})


def migrate_update_repository(config: dict[str, Any]) -> bool:
    """Migrate only known obsolete defaults; preserve user-selected repositories."""
    current = str(config.get("update_repo", "")).strip()
    if not current or current in LEGACY_UPDATE_REPOSITORIES:
        target = str(DEFAULT_CONFIG["update_repo"])
        changed = current != target
        config["update_repo"] = target
        return changed
    return False


def user_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    directory = Path(base) / "ISH" if base else Path.home() / ".ish"
    legacy_directory = Path(base) / "MoyaIshka" if base else Path.home() / ".moya_ishka"
    if legacy_directory.is_dir() and not legacy_directory.is_symlink():
        directory.mkdir(parents=True, exist_ok=True)
        for legacy_item in legacy_directory.rglob("*"):
            if legacy_item.is_symlink():
                continue
            destination = directory / legacy_item.relative_to(legacy_directory)
            if legacy_item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(legacy_item, destination)
                except OSError:
                    pass
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def default_backup_directory() -> Path:
    """Place backups beside, never inside, the replaceable application folder."""
    app_folder = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return app_folder.parent / "ISH_Backups"


DATA_DIR = user_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "assistant.db"
CLOUD_SESSION_PATH = DATA_DIR / "cloud_session.dat"
GOOGLE_DRIVE_SESSION_PATH = DATA_DIR / "google_drive_session.dat"
BACKUP_UPLOAD_QUEUE_PATH = DATA_DIR / "backup_upload_queue.json"
BACKUP_SUPABASE_UPLOAD_QUEUE_PATH = DATA_DIR / "backup_supabase_upload_queue.json"
if os.environ.get("APPDATA"):
    LEGACY_DATA_DIR = Path(os.environ["APPDATA"]) / "CustomAI"
else:
    LEGACY_DATA_DIR = Path.home() / ".custom_ai"

DEFAULT_CONFIG: dict[str, Any] = {
    "assistant_name": "ISH",
    "role": "Универсальный персональный ИИ-помощник",
    "personality": "Дружелюбный, внимательный, любознательный и спокойный. Действуй инициативно, но не навязывайся.",
    "style": "Отвечай по-русски, понятно и по делу. Используй структуру, когда она помогает. Не повторяй вопрос пользователя.",
    "instructions": "Не выдумывай факты и не обещай действий, которые не можешь выполнить. Когда данных недостаточно, честно обозначай неопределённость.",
    "mode": "Авто",
    "online_url": "https://api.openai.com/v1/chat/completions",
    "online_model": "gpt-4.1-mini",
    "online_api_key_protected": "",
    "online_api_key_plain": "",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:3b",
    "temperature": 0.7,
    "theme": "Тёмная",
    "font_family": "Segoe UI",
    "font_size": 12,
    "memory": [],
    "memory_metadata": [],
    "auto_memory": True,
    "memory_semantic_enabled": True,
    "memory_embedding_model": "nomic-embed-text",
    "auto_backup_enabled": True,
    "backup_retention_count": 7,
    "backup_dir": "",
    "backup_cloud_enabled": True,
    "backup_cloud_retention_count": 7,
    "backup_supabase_enabled": False,
    "backup_supabase_retention_count": 7,
    "backup_legacy_migrated": False,
    "voice_tts": False,
    "voice_engine": "system",
    "tts_voice_id": "",
    "tts_rate": 175,
    "microphone_enabled": False,
    "plugins_enabled": False,
    "update_repo": "MrNike227/MoyaIshka",
    "auto_update_check": True,
    "auto_cleanup_old_versions": True,
    "install_dir": "",
    "install_dir_user_selected": False,
    "install_root_dir": "",
    "updates_dir": "",
    "github_pr_repo": "MrNike227/MoyaIshka",
    "github_pr_base": "main",
    "github_pr_token_protected": "",
    "github_pr_token_plain": "",
    "web_search_enabled": True,
    "auto_search_current": True,
    "use_research_library": True,
    "research_auto_enabled": True,
    "research_auto_user_configured": False,
    "research_topics": "Искусственный интеллект и новые модели\nPython и разработка программного обеспечения\nWindows и безопасность компьютера\nНаучно-технические разработки",
    "research_interval_hours": 3,
    "research_results_limit": 10,
    "research_fetch_pages": 5,
    "cloud_primary_provider": "google_drive",
    "google_drive_client_id": "",
    "google_drive_storage_limit_gb": 10,
    "cloud_url": "",
    "cloud_publishable_key": "",
    "cloud_email": "",
    "cloud_auto_sync": True,
    "cloud_auto_sync_user_configured": False,
    "cloud_sync_interval_minutes": 5,
    "cloud_modified_at": "",
    "background_ram_limit_mb": 5120,
    "background_min_available_ram_mb": 8192,
    "background_cpu_limit_percent": 85,
    "developer_architect_model": "",
    "developer_coder_model": "",
    "developer_reviewer_model": "",
}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ISH — настраиваемый настольный ИИ-помощник для Windows 10/11.

Базовая версия использует только стандартную библиотеку Python и Tkinter.
Для чтения PDF и DOCX поддерживаются необязательные пакеты pypdf и python-docx.
"""
from __future__ import annotations

# Standard library
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

# Lightweight test entry point: avoid importing the desktop application in Sandbox mode.
if __name__ == "__main__" and len(sys.argv) >= 4 and sys.argv[1] == "--run-proposal-tests":
    from improvement_testing import run_proposal_tests_cli
    raise SystemExit(run_proposal_tests_cli(sys.argv[2], sys.argv[3]))

# Required encryption dependency; keep imports explicit for PyInstaller analysis.
from cryptography import __version__ as CRYPTOGRAPHY_VERSION
from cryptography.exceptions import InvalidTag as _CryptoInvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _CryptoAESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt as _CryptoScrypt

# Core desktop interface, memory and plugin services.
from avatar_widget import AvatarWindow
from auto_memory import extract_memory_candidate
from context_engine import trim_conversation_context
from conversation_store import Store, load_json, now_iso, pretty_time
from intelligent_memory import (
    MEMORY_CONTEXT_END,
    MEMORY_CONTEXT_START,
    add_or_update_memory,
    edit_memory_entry as edit_memory_record,
    merge_memory_data,
    normalize_memory_metadata,
    select_memory_records,
)
from plugin_manager import PluginManager
from resource_governor import ResourceGovernor
from secure_storage import DATA_BLOB, dpapi_transform, protect_api_key, unprotect_api_key, unprotect_github_pr_token

# Backup and cloud storage integrations.
from backup_cloud import (
    BackupEncryptionError,
    decrypt_backup_file,
    encrypt_backup_file,
    sha256_file as backup_sha256_file,
)
from backup_manager import (
    copy_verified_backups,
    create_backup,
    inspect_backup,
    maybe_create_daily_backup,
    restore_backup,
)
from cloud_sync import (
    CloudSyncError,
    SupabaseCloudClient,
    decrypt_vault,
    delete_protected_session,
    encrypt_vault,
    load_protected_session,
    save_protected_session,
    snapshot_digest,
)
from google_drive_sync import (
    GoogleDriveError,
    GoogleDriveVaultClient,
    backup_file_md5,
)
from supabase_backup import (
    MAX_SUPABASE_FILE_BYTES,
    SupabaseBackupClient,
    SupabaseBackupError,
)

# Self-development, dependency analysis and safe proposal delivery.
from background_developer import run_background_development
from github_pr import (
    GitHubProposalError,
    create_draft_pull_request,
    create_draft_pull_request_from_bundle,
    find_matching_tested_proposal_bundle,
)
from improvement_delivery import (
    build_improvement_chat_context,
    default_install_root,
    ensure_install_layout,
    load_chat_improvement_ideas,
    resolve_install_layout,
    resolve_updates_directory,
    save_change_bundle,
    save_chat_improvement_idea,
    save_improvement_suggestions,
    save_multi_change_bundle,
)
from improvement_testing import test_change_bundle
from module_dependency_analyzer import (
    analyze_module_dependencies,
    build_architecture_intelligence_context,
    build_dependency_context,
    build_project_architecture_index,
    format_dependency_report,
    format_project_architecture_index,
)
from architecture_knowledge import (
    format_recent_architecture_lessons,
    refresh_architecture_knowledge,
)
from self_improvement import (
    MAX_SELF_IMPROVEMENT_CONTEXT_CHARS,
    apply_multi_file_unified_diff,
    apply_patch_with_backup,
    apply_unified_diff,
    build_model_source_context,
    build_multi_file_repair_context,
    editable_project_files,
    editable_test_files,
    extract_unified_diff,
    generate_validated_multi_file_unified_diff,
    generate_validated_unified_diff,
    parse_improvement_suggestions,
    project_dir,
    related_test_path,
    split_multi_file_unified_diff,
)

# Updates, voice input/output, desktop control and online research.
from temporary_storage import configure_temporary_storage, get_temp_directory, resolve_container_root
from updater import check_latest_release, download_verified_update
from updater_helper import (
    cleanup_old_application_copies,
    delete_application_copy,
    ensure_install_dir_writable,
    install_from_source,
    launch_windows_directory_replacement,
    launch_windows_replacement,
    resolve_install_dir,
    scan_application_copies,
    sha256_file,
    user_install_dir,
    validate_app_directory,
)
from voice_assistant import listen_once, speak_text, unload_piper_voice
from voice_manager import (
    VOICE_CATALOG,
    delete_voice,
    download_voice,
    installed_voice_ids,
    is_voice_installed,
    voice_label,
    voice_paths,
)
from web_research import (
    ResearchError,
    ResearchLibrary,
    format_research_digest,
    search_and_fetch,
)
from windows_control import handle_voice_command, launch_app, open_known_folder
from windows_sandbox import (
    get_windows_sandbox_status,
    record_windows_sandbox_install,
    request_windows_sandbox_install,
    wait_for_install_result,
)

# ISHApp feature modules — extracted methods keep their API through mixins.
import app_configuration as _app_configuration
import app_helpers as _app_helpers
import app_initialization_interface as _app_initialization_interface
import app_lifecycle_interface as _app_lifecycle_interface
import app_runtime as _app_runtime
import app_startup as _app_startup
import backup_interface as _backup_interface
import chat_interface as _chat_interface
import cloud_interface as _cloud_interface
import memory_interface as _memory_interface
import model_settings_interface as _model_settings_interface
import plugin_interface as _plugin_interface
import research_interface as _research_interface
import self_improvement_interface as _self_improvement_interface
import settings_interface as _settings_interface
import ui_components as _ui_components
import ui_pages_interface as _ui_pages_interface
import ui_theme_interface as _ui_theme_interface
import update_interface as _update_interface
import voice_interface as _voice_interface

APP_NAME = _app_configuration.APP_NAME
APP_VERSION = _app_configuration.APP_VERSION
MAX_CONTEXT_MESSAGES = _app_configuration.MAX_CONTEXT_MESSAGES
MAX_ATTACHMENT_CHARS = _app_configuration.MAX_ATTACHMENT_CHARS
LEGACY_UPDATE_REPOSITORIES = _app_configuration.LEGACY_UPDATE_REPOSITORIES
migrate_update_repository = _app_configuration.migrate_update_repository
user_data_dir = _app_configuration.user_data_dir
default_backup_directory = _app_configuration.default_backup_directory
DATA_DIR = _app_configuration.DATA_DIR
CONFIG_PATH = _app_configuration.CONFIG_PATH
DB_PATH = _app_configuration.DB_PATH
CLOUD_SESSION_PATH = _app_configuration.CLOUD_SESSION_PATH
GOOGLE_DRIVE_SESSION_PATH = _app_configuration.GOOGLE_DRIVE_SESSION_PATH
BACKUP_UPLOAD_QUEUE_PATH = _app_configuration.BACKUP_UPLOAD_QUEUE_PATH
BACKUP_SUPABASE_UPLOAD_QUEUE_PATH = _app_configuration.BACKUP_SUPABASE_UPLOAD_QUEUE_PATH
LEGACY_DATA_DIR = _app_configuration.LEGACY_DATA_DIR
DEFAULT_CONFIG = _app_configuration.DEFAULT_CONFIG

resource_path = _app_helpers.resource_path
prepare_source_workspace = _app_helpers.prepare_source_workspace
atomic_json_save = _app_helpers.atomic_json_save
normalize_url = _app_helpers.normalize_url
post_json = _app_helpers.post_json
extract_openai_content = _app_helpers.extract_openai_content
read_attachment = _app_helpers.read_attachment

migrate_staged_exe_on_first_launch = _app_startup.migrate_staged_exe_on_first_launch
confirm_update_startup = _app_startup.confirm_update_startup
_handle_update_confirmation_args = _app_startup._handle_update_confirmation_args
_packaged_import_self_test = _app_startup._packaged_import_self_test
main = _app_startup.main
PurpleCheckbox = _ui_components.PurpleCheckbox
class ISHApp(
    _app_initialization_interface.ApplicationInitializationMixin,
    _ui_theme_interface.UIThemeMixin,
    _ui_pages_interface.UIPageMixin,
    _chat_interface.ChatInterfaceMixin,
    _research_interface.ResearchInterfaceMixin,
    _cloud_interface.CloudInterfaceMixin,
    _settings_interface.SettingsInterfaceMixin,
    _backup_interface.BackupInterfaceMixin,
    _voice_interface.VoiceInterfaceMixin,
    _memory_interface.MemoryInterfaceMixin,
    _plugin_interface.PluginInterfaceMixin,
    _self_improvement_interface.SelfImprovementInterfaceMixin,
    _update_interface.UpdateInterfaceMixin,
    _model_settings_interface.ModelSettingsMixin,
    _app_lifecycle_interface.AppLifecycleMixin,
):
    """Backward-compatible public application class; implementations live in feature mixins."""
    pass
# Bind completed main.py globals to the feature mixins.
_app_runtime.bind_main_globals(
    globals(),
    _app_configuration, _app_helpers, _app_initialization_interface,
    _app_lifecycle_interface, _app_startup, _backup_interface, _chat_interface,
    _cloud_interface, _memory_interface, _model_settings_interface,
    _plugin_interface, _research_interface, _self_improvement_interface,
    _settings_interface, _ui_pages_interface, _ui_theme_interface,
    _update_interface, _voice_interface,
)

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test-imports":
        raise SystemExit(_packaged_import_self_test())
    if len(sys.argv) >= 4 and sys.argv[1] == "--apply-update":
        from updater_helper import apply_update
        raise SystemExit(apply_update(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "0"))
    main()

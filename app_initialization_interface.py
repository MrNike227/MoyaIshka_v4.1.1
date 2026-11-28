# -*- coding: utf-8 -*-
"""Window and application initialization for ISHApp."""
from __future__ import annotations

class ApplicationInitializationMixin:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} · Персональный помощник")
        try:
            self.root.iconbitmap(str(resource_path("app_icon.ico")))
        except Exception:
            pass
        # Give Tk multiple raster sizes so Windows does not upscale a tiny icon
        # for a high-DPI taskbar or Alt+Tab preview. Keep references alive.
        self._window_icon_photos = []
        try:
            for icon_name in ("app_icon_256.png", "app_icon_64.png", "app_icon_32.png", "app_icon_16.png"):
                icon_file = resource_path(icon_name)
                if icon_file.is_file():
                    self._window_icon_photos.append(tk.PhotoImage(file=str(icon_file)))
            if self._window_icon_photos:
                self.root.iconphoto(True, *self._window_icon_photos)
        except Exception:
            self._window_icon_photos = []
        # Choose a roomy default without opening larger than the current display.
        screen_w = max(960, self.root.winfo_screenwidth())
        screen_h = max(700, self.root.winfo_screenheight())
        win_w = min(1400, max(960, screen_w - 48))
        win_h = min(920, max(680, screen_h - 64))
        self.root.geometry(f"{win_w}x{win_h}+24+24")
        self.root.minsize(960, 660)

        legacy_config_path = LEGACY_DATA_DIR / "config.json"
        legacy_config = load_json(CONFIG_PATH, None)
        if not isinstance(legacy_config, dict):
            legacy_config = load_json(legacy_config_path, {})
        self.config: dict[str, Any] = dict(DEFAULT_CONFIG)
        if isinstance(legacy_config, dict):
            self.config.update(legacy_config)
        original_memory = self.config.get("memory", [])
        original_memory_metadata = self.config.get("memory_metadata", [])
        migrated_memory, migrated_memory_metadata = normalize_memory_metadata(
            original_memory, original_memory_metadata
        )
        self.config["memory"] = migrated_memory
        self.config["memory_metadata"] = migrated_memory_metadata
        if original_memory != migrated_memory or original_memory_metadata != migrated_memory_metadata:
            atomic_json_save(CONFIG_PATH, self.config)
        if migrate_update_repository(self.config):
            atomic_json_save(CONFIG_PATH, self.config)
        # Improve readability for users upgrading from the former 10pt default.
        # Keep an explicitly selected font family and any larger custom size.
        if isinstance(legacy_config, dict) and "font_family" not in legacy_config:
            self.config["font_family"] = "Segoe UI"
            if int(self.config.get("font_size", 10) or 10) == 10:
                self.config["font_size"] = 11
        try:
            import tkinter.font as tkfont
            installed_fonts = set(tkfont.families(self.root))
        except Exception:
            installed_fonts = set()
        preferred_font = str(self.config.get("font_family", "Segoe UI"))
        if installed_fonts and preferred_font not in installed_fonts:
            preferred_font = "Segoe UI" if "Segoe UI" in installed_fonts else ("Arial" if "Arial" in installed_fonts else "TkDefaultFont")
        self.font_family = preferred_font
        self.config["font_family"] = preferred_font
        # Make the first-run UI comfortably readable while keeping Segoe UI for broad Windows compatibility.
        if int(self.config.get("font_size", 12) or 12) < 12:
            self.config["font_size"] = 12
        self.colors = self._palette_for_theme()
        self.purple_checkboxes: list[tuple[PurpleCheckbox, str]] = []
        # Preserve settings from the first release, which used longer mode labels.
        old_mode = str(self.config.get("mode", "Авто"))
        if old_mode.startswith("Только онлайн"):
            self.config["mode"] = "Только онлайн"
        elif old_mode.startswith("Только локально"):
            self.config["mode"] = "Только локально"
        else:
            self.config["mode"] = "Авто"

        # Remember the folder from which a packaged EXE is currently running.
        # Source/START.bat users get a suggested per-user folder until they choose one.
        running_exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
        if running_exe:
            # The running EXE location is authoritative after a move or rollback.
            self.config["install_dir"] = str(running_exe.parent)
            if running_exe.parent.name.casefold() == "app":
                self.config["install_root_dir"] = str(running_exe.parent.parent)
                self.config["updates_dir"] = str(running_exe.parent.parent / "Updates")
        elif not str(self.config.get("install_dir", "")).strip():
            self.config["install_dir"] = str(resolve_install_dir())
        if not str(self.config.get("install_root_dir", "")).strip():
            self.config["install_root_dir"] = str(default_install_root(
                legacy_install_dir=self.config.get("install_dir"), running_exe=running_exe
            ))
        # The container is a real installation layout, not only a saved setting.
        # Always materialize both sibling folders so Updates exists before the first
        # download/self-analysis, including when upgrading from a legacy App folder.
        install_layout = ensure_install_layout(self.config["install_root_dir"])
        self.config["install_root_dir"] = str(install_layout["root"])
        self.config["updates_dir"] = str(install_layout["updates"])
        if running_exe and running_exe.parent.name.casefold() == "app":
            self.config["install_dir"] = str(install_layout["app"])
        atomic_json_save(CONFIG_PATH, self.config)
        configure_temporary_storage(
            config=self.config,
            config_path=CONFIG_PATH,
            running_path=running_exe,
            source_root=Path(__file__).resolve().parent,
        )

        # Enable the requested background research profile when upgrading from releases
        # where it was opt-in by default and the user has not explicitly configured it.
        if not self.config.get("research_auto_user_configured", False):
            self.config["research_auto_enabled"] = True
            if not str(self.config.get("research_topics", "")).strip():
                self.config["research_topics"] = DEFAULT_CONFIG["research_topics"]
            self.config["research_interval_hours"] = min(3, int(self.config.get("research_interval_hours", 3) or 3))
        if not self.config.get("research_limits_user_configured", False):
            self.config["research_results_limit"] = 10
            self.config["research_fetch_pages"] = 5
        if not self.config.get("cloud_auto_sync_user_configured", False):
            self.config["cloud_auto_sync"] = True
        # Preserve the user's 5-GiB AI soft budget and an 8-GiB reserve for other apps.
        self.config["background_ram_limit_mb"] = max(1024, min(int(self.config.get("background_ram_limit_mb", 5120)), 5120))
        if int(self.config.get("background_min_available_ram_mb", 4096) or 0) < 8192:
            self.config["background_min_available_ram_mb"] = 8192

        self.api_key = unprotect_api_key(self.config)
        self.resource_governor = ResourceGovernor(
            max_ram_mb=int(self.config.get("background_ram_limit_mb", 5120)),
            min_available_ram_mb=int(self.config.get("background_min_available_ram_mb", 8192)),
            cpu_pause_percent=int(self.config.get("background_cpu_limit_percent", 85)),
        )
        self.resource_governor.start_monitor(interval_seconds=1.5)
        self.cloud_session = load_protected_session(CLOUD_SESSION_PATH)
        self.google_drive_session = load_protected_session(GOOGLE_DRIVE_SESSION_PATH)
        self.google_drive_session_ready = self._is_google_drive_session_ready(self.google_drive_session)
        self.cloud_sync_busy = False
        self.cloud_sync_dirty = False
        self.cloud_sync_after_id: str | None = None
        self.cloud_sync_periodic_id: str | None = None
        self.cloud_session_ready = bool(self.cloud_session.get("session", {}).get("access_token") and self.cloud_session.get("e2e_passphrase"))
        self.store = Store(DB_PATH)
        self.research_library = ResearchLibrary(DATA_DIR / "research_library.json", max_items=1000)
        self.store.import_legacy_history(LEGACY_DATA_DIR / "history.json")
        if not CONFIG_PATH.exists() and isinstance(legacy_config, dict) and legacy_config:
            # Preserve settings from version 1 and move the protected key into the new data folder.
            try:
                protected, plain = protect_api_key(self.api_key)
                self.config["online_api_key_protected"] = protected
                self.config["online_api_key_plain"] = plain
                atomic_json_save(CONFIG_PATH, self.config)
            except Exception:
                pass
        self.current_chat_id = self.store.ensure_conversation()
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.avatar: AvatarWindow | None = None
        self.plugin_manager = PluginManager(DATA_DIR, enabled_python=bool(self.config.get("plugins_enabled", False)))
        self.pending_patch_text = ""
        self.pending_patch_target = ""
        self.improvement_suggestions: list[dict[str, str]] = []
        self.improvement_analysis_busy = False
        self.improvement_patch_busy = False
        self.background_development_busy = False
        self.improvement_test_busy = False
        self.improvement_suggestions_target = ""
        self._auto_improvement_after_id: str | None = None
        self.staged_update_path: Path | None = None
        self.staged_update_version = ""
        self._last_update_check_day = ""
        self.backup_working = False
        self.backup_upload_working = False
        self._database_restore_in_progress = False
        self._deferred_restore_events: list[tuple[str, Any]] = []
        self.backup_migration_lock = threading.Lock()
        self.cloud_backup_dialog: tk.Toplevel | None = None
        self.cloud_backup_listbox: tk.Listbox | None = None
        self.cloud_backup_status_var: tk.StringVar | None = None
        self.cloud_backup_items: list[dict[str, Any]] = []
        self.supabase_backup_dialog: tk.Toplevel | None = None
        self.supabase_backup_listbox: tk.Listbox | None = None
        self.supabase_backup_status_var: tk.StringVar | None = None
        self.supabase_backup_items: list[dict[str, Any]] = []
        self.busy = False
        self.voice_busy = False
        self.voice_cancel_event: threading.Event | None = None
        self.voice_download_busy = False
        self.voice_download_progress_value = 0
        self.research_busy = False
        self.windows_sandbox_install_busy = False
        self.windows_sandbox_status_busy = False
        self._auto_research_after_id: str | None = None
        self.pending_attachment: tuple[str, str] | None = None
        self.search_var = tk.StringVar()
        self.chat_mode_var = tk.StringVar(value=self.config.get("mode", "Авто"))
        self.chat_title_var = tk.StringVar(value="Новый диалог")
        self.status_var = tk.StringVar(value="Готов к работе")

        self._build_styles()
        self._build_layout()
        self._apply_theme()
        self._refresh_chat_list()
        self._render_current_chat()
        self.show_page("chat")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-n>", lambda _e: self.new_chat())
        self.root.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.root.bind_all("<Button-4>", lambda e: self._on_global_mousewheel(e, -1), add="+")
        self.root.bind_all("<Button-5>", lambda e: self._on_global_mousewheel(e, 1), add="+")
        self.root.after(100, self._process_events)
        self.root.after(250, self._apply_windows_titlebar_theme)
        self.root.after(450, self._apply_high_dpi_windows_icon)
        self.root.after(4500, self._schedule_automatic_backup)
        self.root.after(20000, self._schedule_backup_upload_retry)
        self.root.after(6500, self._maybe_check_updates)
        self.root.after(12000, self._schedule_auto_research)
        self.root.after(1800, self.refresh_windows_sandbox_status)
        if bool(self.config.get("self_improve_auto_enabled", False)):
            self.root.after(25000, self._run_scheduled_improvement_analysis)
        if self._any_cloud_session_ready() and bool(self.config.get("cloud_auto_sync", True)):
            self.root.after(18000, self._start_cloud_sync)

    # ---------- visual shell ----------

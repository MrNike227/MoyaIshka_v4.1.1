# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class SettingsInterfaceMixin:
    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    # ---------- clipboard and export ----------
    def _show_text_context_menu(self, event: tk.Event) -> None:
        try:
            self.chat_context.tk_popup(event.x_root, event.y_root)
        finally:
            self.chat_context.grab_release()

    def copy_selection(self) -> None:
        try:
            selected = self.chat_view.get("sel.first", "sel.last")
        except tk.TclError:
            selected = ""
        if selected:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            self._set_status("Выделенный текст скопирован")

    def copy_last_answer(self) -> None:
        rows = self.store.get_messages(self.current_chat_id)
        answer = next((row["content"] for row in reversed(rows) if row["role"] == "assistant"), "")
        if not answer:
            self._set_status("В этом диалоге пока нет ответа ИИ")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(answer)
        self._set_status("Последний ответ скопирован")

    def export_chat(self) -> None:
        row = self.store.get_conversation(self.current_chat_id)
        title = (row["title"] if row else "Диалог").replace("/", "-").replace("\\", "-")
        path = filedialog.asksaveasfilename(title="Экспортировать диалог", defaultextension=".md", initialfile=f"{title}.md", filetypes=[("Markdown", "*.md"), ("Текст", "*.txt")])
        if not path:
            return
        try:
            Path(path).write_text(self.store.export_markdown(self.current_chat_id), encoding="utf-8")
            self._set_status(f"Диалог экспортирован: {Path(path).name}")
            messagebox.showinfo("Экспорт готов", f"Файл сохранён:\n{path}")
        except OSError as exc:
            messagebox.showerror("Ошибка экспорта", str(exc))

    # ---------- settings ----------
    def _set_chat_mode(self, _event: tk.Event | None = None) -> None:
        self.config["mode"] = self.chat_mode_var.get()
        self.mode_var.set(self.chat_mode_var.get())
        self._persist_config(show_message=False)
        self._set_status(f"Режим: {self.chat_mode_var.get()}")

    def _toggle_key(self) -> None:
        self.api_key_entry.configure(show="" if self.show_key_var.get() else "●")

    def _persist_config(self, show_message: bool = True) -> bool:
        try:
            protected, plain = protect_api_key(self.api_key_var.get().strip() if hasattr(self, "api_key_var") else self.api_key)
        except Exception as exc:
            messagebox.showerror("Защита API-ключа", f"Не удалось защитить API-ключ средствами Windows. Ключ не сохранён.\n\n{exc}")
            return False
        self.api_key = self.api_key_var.get().strip() if hasattr(self, "api_key_var") else self.api_key
        self.config.update({
            "assistant_name": self.name_var.get().strip() or "Ишка",
            "role": self.role_var.get().strip(),
            "personality": self.personality_var.get().strip(),
            "style": self.style_var.get().strip(),
            "instructions": self.instructions_box.get("1.0", "end").strip(),
            "mode": self.mode_var.get(),
            "online_url": self.online_url_var.get().strip(),
            "online_model": self.online_model_var.get().strip(),
            "online_api_key_protected": protected,
            "online_api_key_plain": plain,
            "ollama_url": self.ollama_url_var.get().strip(),
            "ollama_model": self.ollama_model_var.get().strip(),
            "temperature": round(float(self.temperature_var.get()), 2),
            "theme": self.theme_var.get(),
            "font_size": int(self.font_size_var.get()),
            "font_family": self.font_family_var.get().strip() or "Segoe UI",
            "auto_memory": bool(self.auto_memory_var.get()) if hasattr(self, "auto_memory_var") else bool(self.config.get("auto_memory", True)),
            "memory_semantic_enabled": bool(self.memory_semantic_var.get()) if hasattr(self, "memory_semantic_var") else bool(self.config.get("memory_semantic_enabled", True)),
            "memory_embedding_model": self.memory_embedding_model_var.get().strip()[:120] if hasattr(self, "memory_embedding_model_var") else str(self.config.get("memory_embedding_model", "nomic-embed-text")),
            "auto_backup_enabled": bool(self.auto_backup_var.get()) if hasattr(self, "auto_backup_var") else bool(self.config.get("auto_backup_enabled", True)),
            "backup_retention_count": max(3, min(30, int(self.backup_retention_var.get()))) if hasattr(self, "backup_retention_var") else int(self.config.get("backup_retention_count", 7)),
            "backup_dir": self.backup_dir_var.get().strip() if hasattr(self, "backup_dir_var") else str(self.config.get("backup_dir", "")),
            "backup_cloud_enabled": bool(self.backup_cloud_enabled_var.get()) if hasattr(self, "backup_cloud_enabled_var") else bool(self.config.get("backup_cloud_enabled", True)),
            "backup_cloud_retention_count": max(3, min(30, int(self.backup_cloud_retention_var.get()))) if hasattr(self, "backup_cloud_retention_var") else int(self.config.get("backup_cloud_retention_count", 7)),
            "backup_supabase_enabled": bool(self.backup_supabase_enabled_var.get()) if hasattr(self, "backup_supabase_enabled_var") else bool(self.config.get("backup_supabase_enabled", False)),
            "backup_supabase_retention_count": max(3, min(30, int(self.backup_supabase_retention_var.get()))) if hasattr(self, "backup_supabase_retention_var") else int(self.config.get("backup_supabase_retention_count", 7)),
            "voice_tts": bool(self.voice_tts_var.get()) if hasattr(self, "voice_tts_var") else bool(self.config.get("voice_tts", False)),
            "voice_engine": str(self.config.get("voice_engine", "system")),
            "tts_voice_id": str(self.config.get("tts_voice_id", "")),
            "plugins_enabled": bool(self.python_plugins_var.get()) if hasattr(self, "python_plugins_var") else bool(self.config.get("plugins_enabled", False)),
            "update_repo": self.update_repo_var.get().strip() if hasattr(self, "update_repo_var") else str(self.config.get("update_repo", "")),
            "auto_update_check": bool(self.auto_update_var.get()) if hasattr(self, "auto_update_var") else bool(self.config.get("auto_update_check", True)),
            "auto_cleanup_old_versions": bool(self.auto_cleanup_old_versions_var.get()) if hasattr(self, "auto_cleanup_old_versions_var") else bool(self.config.get("auto_cleanup_old_versions", True)),
            "install_dir": self.update_install_dir_var.get().strip() if hasattr(self, "update_install_dir_var") else str(self.config.get("install_dir", "")),
            "cloud_url": self.cloud_url_var.get().strip() if hasattr(self, "cloud_url_var") else str(self.config.get("cloud_url", "")),
            "cloud_publishable_key": self.cloud_publishable_key_var.get().strip() if hasattr(self, "cloud_publishable_key_var") else str(self.config.get("cloud_publishable_key", "")),
            "cloud_email": self.cloud_email_var.get().strip() if hasattr(self, "cloud_email_var") else str(self.config.get("cloud_email", "")),
            "cloud_auto_sync": bool(self.cloud_auto_sync_var.get()) if hasattr(self, "cloud_auto_sync_var") else bool(self.config.get("cloud_auto_sync", False)),
        })
        self.font_family = str(self.config.get("font_family", "Segoe UI"))
        self.plugin_manager.enabled_python = bool(self.config.get("plugins_enabled", False))
        self.config["cloud_modified_at"] = now_iso()
        atomic_json_save(CONFIG_PATH, self.config)
        self.chat_mode_var.set(self.config["mode"])
        self.chat_title_var.set(self.store.get_conversation(self.current_chat_id)["title"])
        self.chat_name_label.configure(text=self.chat_title_var.get())
        self._apply_theme()
        self._render_current_chat()
        self.chat_view.configure(font=(self.font_family, int(self.config["font_size"])))
        self.input_box.configure(font=(self.font_family, int(self.config["font_size"])))
        self.instructions_box.configure(font=(self.font_family, 11))
        self._refresh_chat_list()
        if show_message:
            messagebox.showinfo("Настройки сохранены", f"Изменения применены.\n\nПапка данных:\n{DATA_DIR}")
        self._set_status("Настройки сохранены")
        self._schedule_cloud_sync()
        return True

    def save_settings(self) -> None:
        self._persist_config(show_message=True)

    def reset_settings(self) -> None:
        if not messagebox.askyesno("Сбросить настройки", "Вернуть имя, характер и параметры подключения к значениям по умолчанию? История чатов и память не удалятся."):
            return
        for key, value in DEFAULT_CONFIG.items():
            if key in {"memory", "memory_metadata"}:
                continue
            self.config[key] = value
        self.api_key = ""
        self._reload_settings_controls()
        self._persist_config(show_message=False)
        self._set_status("Настройки сброшены")
        messagebox.showinfo("Готово", "Настройки сброшены. История и память сохранены.")

    def _reload_settings_controls(self) -> None:
        self.name_var.set(self.config["assistant_name"])
        self.role_var.set(self.config["role"])
        self.personality_var.set(self.config["personality"])
        self.style_var.set(self.config["style"])
        self.mode_var.set(self.config["mode"])
        self.online_url_var.set(self.config["online_url"])
        self.online_model_var.set(self.config["online_model"])
        self.api_key_var.set("")
        self.ollama_url_var.set(self.config["ollama_url"])
        self.ollama_model_var.set(self.config["ollama_model"])
        self.temperature_var.set(self.config["temperature"])
        self.theme_var.set(self.config["theme"])
        self.font_size_var.set(str(self.config["font_size"]))
        self.font_family_var.set(str(self.config.get("font_family", "Segoe UI")))
        self.instructions_box.delete("1.0", "end")
        self.instructions_box.insert("1.0", self.config["instructions"])
        if hasattr(self, "auto_memory_var"):
            self.auto_memory_var.set(bool(self.config.get("auto_memory", True)))
        if hasattr(self, "memory_semantic_var"):
            self.memory_semantic_var.set(bool(self.config.get("memory_semantic_enabled", True)))
        if hasattr(self, "memory_embedding_model_var"):
            self.memory_embedding_model_var.set(str(self.config.get("memory_embedding_model", "nomic-embed-text")))
        if hasattr(self, "auto_backup_var"):
            self.auto_backup_var.set(bool(self.config.get("auto_backup_enabled", True)))
            self.backup_retention_var.set(str(self.config.get("backup_retention_count", 7)))
            if hasattr(self, "backup_dir_var"):
                self.backup_dir_var.set(str(self._backup_directory()))
            if hasattr(self, "backup_cloud_enabled_var"):
                self.backup_cloud_enabled_var.set(bool(self.config.get("backup_cloud_enabled", True)))
                self.backup_cloud_retention_var.set(str(self.config.get("backup_cloud_retention_count", 7)))
                if hasattr(self, "backup_supabase_enabled_var"):
                    self.backup_supabase_enabled_var.set(bool(self.config.get("backup_supabase_enabled", False)))
                    self.backup_supabase_retention_var.set(str(self.config.get("backup_supabase_retention_count", 7)))
        if hasattr(self, "voice_tts_var"):
            self.voice_tts_var.set(bool(self.config.get("voice_tts", False)))
        if hasattr(self, "tts_voice_combo"):
            self._refresh_tts_voice_controls()
        if hasattr(self, "python_plugins_var"):
            self.python_plugins_var.set(bool(self.config.get("plugins_enabled", False)))
            self.plugin_manager.enabled_python = bool(self.config.get("plugins_enabled", False))
        if hasattr(self, "update_repo_var"):
            self.update_repo_var.set(str(self.config.get("update_repo", "")))
        if hasattr(self, "auto_update_var"):
            self.auto_update_var.set(bool(self.config.get("auto_update_check", True)))
        if hasattr(self, "auto_cleanup_old_versions_var"):
            self.auto_cleanup_old_versions_var.set(bool(self.config.get("auto_cleanup_old_versions", True)))
        if hasattr(self, "web_enabled_var"):
            self.web_enabled_var.set(bool(self.config.get("web_search_enabled", True)))
            self.auto_search_current_var.set(bool(self.config.get("auto_search_current", False)))
            self.use_research_library_var.set(bool(self.config.get("use_research_library", True)))
            self.research_auto_var.set(bool(self.config.get("research_auto_enabled", False)))
            self.research_topics_box.delete("1.0", "end")
            self.research_topics_box.insert("1.0", str(self.config.get("research_topics", "")))
            self.research_interval_var.set(str(self.config.get("research_interval_hours", 12)))
            self.research_results_var.set(str(self.config.get("research_results_limit", 5)))
            self.research_fetch_var.set(str(self.config.get("research_fetch_pages", 3)))

    def save_resource_settings(self) -> None:
        try:
            ram_mb = int(self.background_ram_var.get())
            cpu_limit = int(self.background_cpu_var.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Нагрузка компьютера", "Выбери допустимый лимит памяти и порог CPU.")
            return
        self.config["background_ram_limit_mb"] = max(1024, min(ram_mb, 5120))
        self.config["background_min_available_ram_mb"] = 8192
        self.config["background_cpu_limit_percent"] = max(60, min(cpu_limit, 98))
        self.resource_governor.configure(
            max_ram_mb=self.config["background_ram_limit_mb"],
            min_available_ram_mb=self.config["background_min_available_ram_mb"],
            cpu_pause_percent=self.config["background_cpu_limit_percent"],
        )
        atomic_json_save(CONFIG_PATH, self.config)
        self.resource_status_var.set(
            f"Применено: бюджет ИИ {ram_mb} МБ; фон приостанавливается около {cpu_limit}% CPU или при свободной ОЗУ менее 8 ГБ."
        )
        self._schedule_cloud_sync()

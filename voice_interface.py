# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class VoiceInterfaceMixin:
    # ---------- Windows controls, voice, plugins, self-improvement, updates ----------
    def _show_action_result(self, result: Any) -> None:
        if result.handled:
            self._render_status_message(result.message, error=not result.success)
            self._set_status(result.message)

    def _run_windows_app(self, name: str) -> None:
        self._show_action_result(launch_app(name))

    def _run_windows_folder(self, name: str) -> None:
        self._show_action_result(open_known_folder(name))

    def _toggle_microphone_access(self) -> None:
        allowed = bool(self.microphone_enabled_var.get())
        self.config["microphone_enabled"] = allowed
        atomic_json_save(CONFIG_PATH, self.config)
        if not allowed:
            self.stop_voice_input(update_permission=False)
            self.voice_status_var.set("Доступ приложения к микрофону выключен. Запись остановлена.")
            self.voice_start_button.configure(state="disabled")
        else:
            self.voice_status_var.set("Доступ разрешён. Микрофон включается только после нажатия «Начать говорить».")
            self.voice_start_button.configure(state="normal")

    def stop_voice_input(self, update_permission: bool = True) -> None:
        if self.voice_cancel_event is not None:
            self.voice_cancel_event.set()
        self.voice_busy = False
        if update_permission and hasattr(self, "microphone_enabled_var"):
            self.microphone_enabled_var.set(False)
            self.config["microphone_enabled"] = False
            atomic_json_save(CONFIG_PATH, self.config)
        if hasattr(self, "voice_start_button"):
            self.voice_start_button.configure(state="disabled" if not bool(self.config.get("microphone_enabled", False)) else "normal")
        if hasattr(self, "voice_stop_button"):
            self.voice_stop_button.configure(state="disabled")
        if hasattr(self, "voice_status_var"):
            self.voice_status_var.set("Микрофон остановлен и отключён.")

    def open_windows_microphone_privacy(self) -> None:
        if os.name != "nt":
            messagebox.showinfo("Микрофон Windows", "Эта ссылка доступна в Windows 10/11.")
            return
        try:
            os.startfile("ms-settings:privacy-microphone")  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Настройки микрофона", f"Не удалось открыть параметры Windows: {exc}")

    def start_voice_input(self) -> None:
        if not bool(self.config.get("microphone_enabled", False)):
            self.voice_status_var.set("Сначала разреши доступ к микрофону переключателем выше.")
            return
        if self.voice_busy:
            self.voice_status_var.set("Микрофон уже слушает. Нажми «Остановить», чтобы прервать запись.")
            return
        self.voice_busy = True
        self.resource_governor.set_foreground_busy(True)
        self.voice_cancel_event = threading.Event()
        cancel_event = self.voice_cancel_event
        self.voice_start_button.configure(state="disabled")
        self.voice_stop_button.configure(state="normal")
        self.voice_status_var.set("Слушаю. Скажи фразу; после паузы запись закончится автоматически.")
        self._set_status("Ожидаю голосовую команду")

        def worker() -> None:
            try:
                recognized = listen_once(language="ru-RU", stop_event=cancel_event)
                if not cancel_event.is_set():
                    self.events.put(("voice_text", recognized))
            except Exception as exc:
                self.events.put(("voice_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _speak_safely(self, text: str) -> None:
        if self.avatar is not None:
            try:
                self.root.after(0, lambda: self.avatar.set_talking(True) if self.avatar else None)
            except Exception:
                pass
        try:
            engine_name = str(self.config.get("voice_engine", "system"))
            model_path = None
            if engine_name == "piper":
                voice_id = str(self.config.get("tts_voice_id", ""))
                if not voice_id or not is_voice_installed(DATA_DIR, voice_id):
                    raise RuntimeError("Выбранный голос не скачан. Открой «Windows и голос» и загрузи голос Piper либо выбери системный голос Windows.")
                model_path = voice_paths(DATA_DIR, voice_id)[0]
            speak_text(text, rate=int(self.config.get("tts_rate", 175)), engine=engine_name, model_path=model_path)
        except Exception as exc:
            self.events.put(("voice_error", str(exc)))
        finally:
            if self.avatar is not None:
                try:
                    self.root.after(0, lambda: self.avatar.set_talking(False) if self.avatar else None)
                except Exception:
                    pass

    def speak_last_answer(self) -> None:
        rows = self.store.get_messages(self.current_chat_id)
        answer = next((row["content"] for row in reversed(rows) if row["role"] == "assistant"), "")
        if not answer:
            self.voice_status_var.set("В этом диалоге пока нет ответа ИИ.")
            return
        self.voice_status_var.set("Озвучиваю последний ответ…")
        threading.Thread(target=self._speak_safely, args=(answer,), daemon=True).start()

    def toggle_avatar(self) -> None:
        if self.avatar is None:
            self.avatar = AvatarWindow(self.root, str(self.config.get("assistant_name", "Ишка")))
            self.voice_status_var.set("Персонаж показан на рабочем столе. Перетаскивай его мышью.")
        elif self.avatar.visible:
            self.avatar.hide()
            self.voice_status_var.set("Персонаж скрыт.")
        else:
            self.avatar.show()
            self.voice_status_var.set("Персонаж показан.")

    def _toggle_voice_tts(self) -> None:
        self.config["voice_tts"] = bool(self.voice_tts_var.get())
        atomic_json_save(CONFIG_PATH, self.config)
        self.voice_status_var.set("Автоозвучивание включено." if self.config["voice_tts"] else "Автоозвучивание выключено.")

    def _selected_tts_voice_id(self) -> str:
        selected = self.tts_voice_var.get() if hasattr(self, "tts_voice_var") else ""
        return str(getattr(self, "_tts_voice_display_to_id", {}).get(selected, ""))

    def _refresh_tts_voice_controls(self) -> None:
        if not hasattr(self, "tts_voice_combo"):
            return
        installed = set(installed_voice_ids(DATA_DIR))
        display_to_id: dict[str, str] = {}
        for voice_id, item in VOICE_CATALOG.items():
            label = voice_label(voice_id)
            if voice_id in installed:
                label += "  ✓ скачан"
            display_to_id[label] = voice_id
        self._tts_voice_display_to_id = display_to_id
        self.tts_voice_combo.configure(values=list(display_to_id.keys()))
        current_id = str(self.config.get("tts_voice_id", ""))
        current_label = next((label for label, voice_id in display_to_id.items() if voice_id == current_id), "")
        if not self.tts_voice_var.get() or self.tts_voice_var.get() not in display_to_id:
            preferred = current_label or next(iter(display_to_id), "")
            self.tts_voice_var.set(preferred)
        engine = str(self.config.get("voice_engine", "system"))
        if engine == "piper" and current_id in installed:
            self.tts_voice_status_var.set(f"Используется локальный голос: {VOICE_CATALOG[current_id]['name']}.")
        elif engine == "piper":
            self.config["voice_engine"] = "system"
            self.tts_voice_status_var.set("Ранее выбранный голос не найден. Временно используется системный голос Windows.")
            atomic_json_save(CONFIG_PATH, self.config)
        else:
            self.tts_voice_status_var.set("Используется системный голос Windows. Выбери голос и нажми «Загрузить голос», чтобы добавить локальную озвучку.")

    def _on_tts_voice_selected(self, _event=None) -> None:
        voice_id = self._selected_tts_voice_id()
        if not voice_id:
            return
        item = VOICE_CATALOG[voice_id]
        if is_voice_installed(DATA_DIR, voice_id):
            self.tts_voice_status_var.set(f"Голос «{item['name']}» уже скачан. Нажми «Прослушать пример» или «Загрузить голос» не требуется.")
        else:
            self.tts_voice_status_var.set(f"Голос «{item['name']}» ещё не скачан. Размер около 60 МБ; загрузка выполняется один раз.")

    def download_selected_tts_voice(self) -> None:
        if self.voice_download_busy:
            return
        voice_id = self._selected_tts_voice_id()
        if not voice_id:
            messagebox.showinfo("Голос озвучивания", "Сначала выбери голос из списка.")
            return
        if is_voice_installed(DATA_DIR, voice_id):
            self.config["tts_voice_id"] = voice_id
            self.config["voice_engine"] = "piper"
            atomic_json_save(CONFIG_PATH, self.config)
            self._refresh_tts_voice_controls()
            return
        item = VOICE_CATALOG[voice_id]
        if not messagebox.askyesno(
            "Загрузить голос",
            f"Загрузить голос «{item['name']}»?\n\nРазмер модели — около 60 МБ. После загрузки голос будет работать локально, без передачи текста в интернет. Продолжить?",
            parent=self.root,
        ):
            return
        self.voice_download_busy = True
        self.tts_voice_progress.configure(value=0)
        self.tts_voice_status_var.set(f"Подготовка загрузки голоса «{item['name']}»…")
        threading.Thread(target=self._download_tts_voice_worker, args=(voice_id,), daemon=True).start()

    def _download_tts_voice_worker(self, voice_id: str) -> None:
        def on_progress(downloaded: int, total: int) -> None:
            self.events.put(("tts_voice_progress", (voice_id, downloaded, total)))
        try:
            download_voice(DATA_DIR, voice_id, progress=on_progress)
            self.events.put(("tts_voice_download_complete", voice_id))
        except Exception as exc:
            self.events.put(("tts_voice_download_error", str(exc)))

    def use_system_tts_voice(self) -> None:
        self.config["voice_engine"] = "system"
        atomic_json_save(CONFIG_PATH, self.config)
        self._refresh_tts_voice_controls()
        self.voice_status_var.set("Выбран системный голос Windows.")

    def delete_selected_tts_voice(self) -> None:
        voice_id = self._selected_tts_voice_id()
        if not voice_id or not is_voice_installed(DATA_DIR, voice_id):
            messagebox.showinfo("Удаление голоса", "Выбранный голос ещё не загружен.")
            return
        name = VOICE_CATALOG[voice_id]["name"]
        if not messagebox.askyesno("Удалить голос", f"Удалить скачанную модель «{name}»?\n\nЭто освободит около 60 МБ. Системный голос Windows останется доступен.", parent=self.root):
            return
        try:
            model_path = voice_paths(DATA_DIR, voice_id)[0]
            unload_piper_voice(model_path)
            delete_voice(DATA_DIR, voice_id)
            if str(self.config.get("tts_voice_id", "")) == voice_id:
                self.config["tts_voice_id"] = ""
                self.config["voice_engine"] = "system"
            atomic_json_save(CONFIG_PATH, self.config)
            self._refresh_tts_voice_controls()
            self.voice_status_var.set(f"Голос «{name}» удалён. Используется системный голос Windows.")
        except Exception as exc:
            messagebox.showerror("Удаление голоса", str(exc))

    def preview_selected_tts_voice(self) -> None:
        voice_id = self._selected_tts_voice_id()
        if not voice_id or not is_voice_installed(DATA_DIR, voice_id):
            messagebox.showinfo("Пример голоса", "Сначала скачай выбранный голос кнопкой «Загрузить голос».")
            return
        model_path = voice_paths(DATA_DIR, voice_id)[0]
        self.tts_voice_status_var.set("Готовлю короткий пример озвучивания…")
        def worker() -> None:
            try:
                speak_text("Привет! Это пример моего голоса. Рада тебя слышать!", engine="piper", model_path=model_path)
                self.events.put(("tts_voice_preview_complete", None))
            except Exception as exc:
                self.events.put(("tts_voice_preview_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()



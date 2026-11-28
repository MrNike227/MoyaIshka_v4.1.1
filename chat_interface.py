# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class ChatInterfaceMixin:
    def show_page(self, key: str) -> None:
        self.pages[key].tkraise()
        self.active_page = key
        for name, button in self.nav_buttons.items():
            button.state(["pressed"] if name == key else ["!pressed"])
        if key == "memory":
            self._refresh_memory_list()
        elif key == "workshop":
            self._refresh_skill_list()
        elif key == "research":
            self._refresh_research_list()

    # ---------- chat navigation ----------
    def _short_chat_time(self, value: str) -> str:
        try:
            stamp = datetime.fromisoformat(value).astimezone()
            today = datetime.now().astimezone().date()
            if stamp.date() == today:
                return stamp.strftime("сегодня · %H:%M")
            if (today - stamp.date()).days == 1:
                return stamp.strftime("вчера · %H:%M")
            if (today - stamp.date()).days < 7:
                return stamp.strftime("%a · %H:%M")
            return stamp.strftime("%d.%m.%y")
        except (ValueError, TypeError):
            return ""

    def _set_chat_card_visual(self, identifier: str, hovered: bool | None = None) -> None:
        parts = self.chat_cards.get(identifier)
        if not parts:
            return
        if hovered is not None:
            parts["hovered"] = hovered
        selected = identifier == self.current_chat_id
        is_hovered = bool(parts.get("hovered", False)) and not selected
        background = self.colors["recent_selected"] if selected else (self.colors["recent_hover"] if is_hovered else self.colors["recent_card"])
        border = self.colors["recent_selected_border"] if selected else (self.colors["recent_hover"] if is_hovered else self.colors["recent_border"])
        parts["card"].configure(bg=background, highlightbackground=border, highlightcolor=border, highlightthickness=2 if selected else 1)
        parts["marker"].configure(bg=self.colors["accent"] if selected else background)
        parts["body"].configure(bg=background)
        parts["top"].configure(bg=background)
        parts["title"].configure(bg=background, fg=self.colors["text"])
        parts["time"].configure(bg=background, fg=self.colors["accent"] if selected else self.colors["muted"])
        parts["preview"].configure(bg=background, fg=self.colors["muted"])

    def _restyle_chat_cards(self) -> None:
        if not hasattr(self, "chat_cards"):
            return
        for identifier in list(self.chat_cards):
            self._set_chat_card_visual(identifier)

    def _bind_chat_card(self, widget: tk.Widget, identifier: str) -> None:
        widget.bind("<Button-1>", lambda _event, chat_id=identifier: self._select_chat_card(chat_id))
        widget.bind("<Button-3>", self._chat_context_menu)
        widget.bind("<Enter>", lambda _event, chat_id=identifier: self._set_chat_card_visual(chat_id, True))
        widget.bind("<Leave>", lambda _event, chat_id=identifier: self._set_chat_card_visual(chat_id, False))
        setattr(widget, "_moya_chat_id", identifier)

    def _refresh_chat_list(self) -> None:
        if not hasattr(self, "chat_list_canvas"):
            return
        rows = self.store.list_conversations(self.search_var.get())
        self.visible_chat_ids = [row["id"] for row in rows]
        for child in self.chat_list_inner.winfo_children():
            child.destroy()
        self.chat_cards = {}
        if hasattr(self, "recent_count_var"):
            self.recent_count_var.set(str(len(rows)))

        if not rows:
            empty = tk.Label(
                self.chat_list_inner,
                text="Здесь будут твои диалоги\nСоздай новый разговор, чтобы начать",
                justify="left", anchor="w", padx=14, pady=22,
                font=(self.font_family, 11), bg=self.colors["sidebar"], fg=self.colors["muted"],
            )
            empty.pack(fill="x", padx=3, pady=5)

        for row in rows:
            identifier = str(row["id"])
            title_text = str(row["title"] or "Новый диалог").strip()
            title_text = title_text if len(title_text) <= 48 else title_text[:45].rstrip() + "…"
            latest = self.store.get_messages(identifier, limit=1)
            snippet = "Начни новый разговор" if not latest else re.sub(r"\s+", " ", str(latest[0]["content"])).strip()
            snippet = snippet if len(snippet) <= 96 else snippet[:93].rstrip() + "…"
            stamp = self._short_chat_time(str(row["updated_at"]))

            selected = identifier == self.current_chat_id
            bg = self.colors["recent_selected"] if selected else self.colors["recent_card"]
            border = self.colors["recent_selected_border"] if selected else self.colors["recent_border"]
            card = tk.Frame(
                self.chat_list_inner, bg=bg, bd=0, relief="flat",
                highlightthickness=2 if selected else 1,
                highlightbackground=border, highlightcolor=border,
            )
            card.pack(fill="x", padx=4, pady=6)
            marker = tk.Frame(card, width=4, bg=self.colors["accent"] if selected else bg, bd=0)
            marker.pack(side="left", fill="y")
            body = tk.Frame(card, bg=bg, bd=0)
            body.pack(side="left", fill="both", expand=True, padx=(13, 11), pady=(12, 12))
            top = tk.Frame(body, bg=bg, bd=0)
            top.pack(fill="x")
            title = tk.Label(
                top, text=title_text, anchor="w", justify="left", wraplength=232,
                font=(self.font_family, 12, "bold"), bg=bg, fg=self.colors["text"],
            )
            title.pack(fill="x", anchor="w")
            time_label = tk.Label(
                body, text=f"◷  {stamp}" if stamp else "", anchor="w", justify="left",
                font=(self.font_family, 10), bg=bg, fg=self.colors["muted"],
            )
            time_label.pack(anchor="w", pady=(4, 0))
            preview = tk.Label(
                body, text=snippet, anchor="w", justify="left", wraplength=232,
                font=(self.font_family, 9), bg=bg, fg=self.colors["muted"],
            )
            preview.pack(fill="x", anchor="w", pady=(6, 0))

            parts = {"card": card, "marker": marker, "body": body, "top": top, "title": title, "time": time_label, "preview": preview, "hovered": False}
            self.chat_cards[identifier] = parts
            for widget in (card, marker, body, top, title, time_label, preview):
                self._bind_chat_card(widget, identifier)

        self.chat_list_inner.update_idletasks()
        self.chat_list_canvas.configure(scrollregion=self.chat_list_canvas.bbox("all"))

    def _select_chat_card(self, identifier: str) -> None:
        if identifier not in self.visible_chat_ids or identifier == self.current_chat_id:
            return
        self.current_chat_id = identifier
        self._refresh_chat_list()
        self._render_current_chat()

    def _on_chat_select(self, _event: tk.Event | None = None) -> None:
        # Compatibility hook retained for older bindings.
        return

    def new_chat(self) -> None:
        if self.busy:
            messagebox.showinfo("Подождите", "Дождитесь ответа текущего ИИ, затем создайте новый диалог.")
            return
        self.current_chat_id = self.store.create_conversation()
        self._refresh_chat_list()
        self._render_current_chat()
        self.show_page("chat")
        self.input_box.focus_set()
        self._schedule_cloud_sync()
        self._set_status("Создан новый диалог")

    def rename_chat(self) -> None:
        row = self.store.get_conversation(self.current_chat_id)
        current = row["title"] if row else "Новый диалог"
        title = simpledialog.askstring("Переименовать диалог", "Новое название:", initialvalue=current, parent=self.root)
        if title and title.strip():
            self.store.rename_conversation(self.current_chat_id, title)
            self._refresh_chat_list()
            self._render_current_chat()
            self._schedule_cloud_sync()

    def delete_chat(self) -> None:
        if self.busy:
            messagebox.showinfo("Подождите", "Нельзя удалить диалог, пока ИИ готовит ответ.")
            return
        if not messagebox.askyesno("Удалить диалог", "Удалить этот диалог и всю его переписку? Это действие нельзя отменить."):
            return
        self.store.delete_conversation(self.current_chat_id)
        self.current_chat_id = self.store.ensure_conversation()
        self._refresh_chat_list()
        self._render_current_chat()
        self._schedule_cloud_sync()
        self._set_status("Диалог удалён")

    def clear_chat(self) -> None:
        if not self.store.get_messages(self.current_chat_id):
            return
        if messagebox.askyesno("Очистить диалог", "Удалить сообщения в этом диалоге? Сам диалог останется."):
            self.store.clear_messages(self.current_chat_id)
            self._render_current_chat()
            self._refresh_chat_list()
            self._schedule_cloud_sync()
            self._set_status("Переписка очищена")

    def _chat_context_menu(self, event: tk.Event) -> None:
        widget: Any = event.widget
        while widget is not None and not hasattr(widget, "_moya_chat_id"):
            widget = getattr(widget, "master", None)
        identifier = getattr(widget, "_moya_chat_id", None) if widget is not None else None
        if identifier:
            self._select_chat_card(str(identifier))
        menu = tk.Menu(self.root, tearoff=False)
        try:
            menu.add_command(label="Новый диалог", command=self.new_chat)
            menu.add_command(label="Переименовать", command=self.rename_chat)
            menu.add_command(label="Экспортировать", command=self.export_chat)
            menu.add_separator()
            menu.add_command(label="Удалить диалог", command=self.delete_chat)
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def chat_more_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Переименовать диалог", command=self.rename_chat)
        menu.add_command(label="Очистить переписку", command=self.clear_chat)
        menu.add_command(label="Удалить диалог", command=self.delete_chat)
        menu.add_separator()
        menu.add_command(label="Открыть папку данных", command=self.open_data_folder)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    # ---------- conversation rendering and input ----------
    def _display_content(self, content: str) -> str:
        match = re.search(r"\n\n\[Контекст файла: ([^\]]+)\]\n", content)
        if match:
            prompt = content[:match.start()].rstrip()
            return (prompt + "\n\n📎 Файл приложен: " + match.group(1) + " (текст файла добавлен к запросу)") if prompt else ("📎 Файл приложен: " + match.group(1))
        return content

    def _render_current_chat(self) -> None:
        if not hasattr(self, "chat_view"):
            return
        row = self.store.get_conversation(self.current_chat_id)
        full_title = str(row["title"] if row else "Новый диалог")
        self.chat_title_var.set(full_title if len(full_title) <= 25 else full_title[:22].rstrip() + "…")
        self.chat_view.configure(state="normal")
        self.chat_view.delete("1.0", "end")
        messages = self.store.get_messages(self.current_chat_id)
        if not messages:
            assistant_name = self.config.get("assistant_name", "Ишка")
            self.chat_view.insert("end", "✦  ДОБРО ПОЖАЛОВАТЬ\n", "meta")
            self.chat_view.insert("end", f"Привет, я {assistant_name}.\n", "welcome_title")
            self.chat_view.insert("end", "Твой личный ИИ для идей, исследований, творчества и повседневных задач.\n\n", "welcome_subtitle")
            self.chat_view.insert("end", "С ЧЕГО НАЧНЁМ?\n", "meta")
            self.chat_view.insert("end", "✧  Объясни сложную тему простыми словами\n", ("quick_prompt", "quick_explain"))
            self.chat_view.insert("end", "◎  Найди свежую информацию в интернете\n", ("quick_prompt", "quick_research"))
            self.chat_view.insert("end", "⌘  Помоги разобраться с Windows\n", ("quick_prompt", "quick_windows"))
            self.chat_view.insert("end", "\nПодключи модель в настройках: локальную через Ollama или облачную через API.\n", "meta")
        else:
            for message in messages:
                self._append_message_to_widget(message["role"], message["content"], message["source"], message["created_at"])
        self.chat_view.configure(state="disabled")
        self.chat_view.see("end")
        self._refresh_chat_list()

    def _append_message_to_widget(self, role: str, content: str, source: str = "", stamp: str = "") -> None:
        is_user = role == "user"
        name = "Вы" if is_user else self.config.get("assistant_name", "Ишка")
        name_tag = "user_name" if is_user else "assistant_name"
        body_tag = "user_body" if is_user else "assistant_body"
        self.chat_view.insert("end", name, name_tag)
        detail = ""
        if source:
            detail += source
        if stamp:
            detail += ("  ·  " if detail else "") + pretty_time(stamp)
        if detail:
            self.chat_view.insert("end", "  ·  " + detail, "meta")
        self.chat_view.insert("end", "\n")
        self.chat_view.insert("end", self._display_content(content) + "\n\n", body_tag)

    def _quick_prompt_click(self, event: tk.Event) -> str:
        index = self.chat_view.index(f"@{event.x},{event.y}")
        tags = self.chat_view.tag_names(index)
        prompt_map = {
            "quick_explain": "Объясни мне одну сложную тему простыми словами и приведи понятный пример.",
            "quick_research": "Поищи в интернете свежую и проверенную информацию о последних важных событиях в технологиях.",
            "quick_windows": "Помоги проверить и улучшить работу моего компьютера с Windows 10.",
        }
        for tag, prompt in prompt_map.items():
            if tag in tags:
                self.input_box.delete("1.0", "end")
                self.input_box.insert("1.0", prompt)
                self.input_box.focus_set()
                return "break"
        return "break"

    def _render_status_message(self, text: str, error: bool = False) -> None:
        self.chat_view.configure(state="normal")
        self.chat_view.insert("end", "Система\n", "meta")
        self.chat_view.insert("end", text + "\n\n", "error" if error else "meta")
        self.chat_view.configure(state="disabled")
        self.chat_view.see("end")

    def _input_return(self, event: tk.Event) -> str | None:
        # Shift+Enter keeps the Text widget's normal newline behavior.
        if int(getattr(event, "state", 0)) & 0x0001:
            return None
        self.send_message()
        return "break"

    @staticmethod
    def _scroll_canvas_from_mousewheel(event: tk.Event, canvas: tk.Canvas) -> str:
        """Route wheel input from a short embedded Text field to its page."""
        button = int(getattr(event, "num", 0) or 0)
        if button == 4:
            steps = -1
        elif button == 5:
            steps = 1
        else:
            delta = int(getattr(event, "delta", 0))
            if not delta:
                return "break"
            steps = int(-delta / 120)
            if steps == 0:
                steps = -1 if delta > 0 else 1
        try:
            canvas.yview_scroll(steps, "units")
        except tk.TclError:
            pass
        return "break"

    def _on_global_mousewheel(self, event: tk.Event, linux_direction: int = 0) -> str | None:
        """Scroll the containing page before an inner text/list widget."""
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            return None
        if linux_direction:
            steps = linux_direction
        else:
            delta = int(getattr(event, "delta", 0))
            if not delta:
                return None
            steps = int(-delta / 120)
            if steps == 0:
                steps = -1 if delta > 0 else 1

        # A Text widget embedded in the Settings page receives the pointer
        # first and otherwise captures the wheel, preventing its parent
        # Canvas from scrolling. Prefer the nearest ancestor Canvas so the
        # whole settings page moves over fields such as "Мои дополнительные
        # правила". Standalone Text/Listbox widgets keep their own scrolling.
        ancestor = widget
        while ancestor is not None and ancestor is not self.root:
            try:
                if isinstance(ancestor, tk.Canvas):
                    ancestor.yview_scroll(steps, "units")
                    return "break"
                ancestor = ancestor.master
            except (tk.TclError, AttributeError):
                return None

        ancestor = widget
        while ancestor is not None and ancestor is not self.root:
            try:
                if isinstance(ancestor, (tk.Text, tk.Listbox, ttk.Treeview)):
                    ancestor.yview_scroll(steps, "units")
                    return "break"
                ancestor = ancestor.master
            except (tk.TclError, AttributeError):
                return None
        return None

    def _send_shortcut(self, _event: tk.Event) -> str:
        self.send_message()
        return "break"

    def attach_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Прикрепить документ",
            filetypes=[("Поддерживаемые документы", "*.txt *.md *.csv *.json *.py *.log *.xml *.html *.htm *.yaml *.yml *.ini *.sql *.pdf *.docx"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            text = read_attachment(Path(path))
        except Exception as exc:
            messagebox.showerror("Не удалось прочитать файл", str(exc))
            return
        self.pending_attachment = (Path(path).name, text)
        self.attachment_label_var.set(f"📎 {Path(path).name} · текст будет добавлен к следующему запросу     ×")
        self._set_status(f"Файл прикреплён: {Path(path).name}")

    def send_message(self) -> None:
        if self.busy:
            return
        prompt = self.input_box.get("1.0", "end").strip()
        if not prompt and not self.pending_attachment:
            return
        if self.pending_attachment:
            filename, file_text = self.pending_attachment
            content = (prompt + "\n\n" if prompt else "Проанализируй прикреплённый файл.\n\n") + f"[Контекст файла: {filename}]\n" + file_text
        else:
            content = prompt
        had_attachment = self.pending_attachment is not None
        windows_action = handle_voice_command(prompt) if not had_attachment else None
        plugin_response = None
        try:
            plugin_response = self.plugin_manager.try_handle_command(prompt)
        except Exception as exc:
            messagebox.showerror("Ошибка Python-плагина", f"Плагин завершился с ошибкой:\n{exc}")
            return
        self.input_box.delete("1.0", "end")
        self.pending_attachment = None
        self.attachment_label_var.set("")
        self.store.add_message(self.current_chat_id, "user", content)
        idea_saved = False
        if not had_attachment:
            try:
                idea_saved = save_chat_improvement_idea(
                    self._updates_directory(), prompt,
                ) is not None
            except Exception:
                # Saving an optional idea must never block the regular chat.
                idea_saved = False
        self._schedule_cloud_sync()
        if bool(self.config.get("auto_memory", True)) and not had_attachment:
            candidate = extract_memory_candidate(prompt)
            if candidate:
                memories, metadata, action = add_or_update_memory(
                    self.config.get("memory", []), self.config.get("memory_metadata", []),
                    candidate, source="automatic",
                )
                if action in {"added", "superseded", "duplicate"}:
                    self.config["memory"] = memories
                    self.config["memory_metadata"] = metadata
                    atomic_json_save(CONFIG_PATH, self.config)
                    self._refresh_memory_list()
                    self._schedule_cloud_sync()
                    status = "Полезный факт сохранён в память"
                    if action == "superseded":
                        status = "Новое сведение обновило противоречащую запись памяти"
                    self._set_status(status)
        web_query = self._extract_web_query(prompt) if not had_attachment else ""
        if web_query and bool(self.config.get("web_search_enabled", True)):
            self._render_current_chat()
            self.busy = True
            self.resource_governor.set_foreground_busy(True)
            if self.avatar is not None:
                self.avatar.set_talking(True)
            self.send_button.configure(state="disabled", text="Ищу в интернете…")
            self._set_status(
                "Ищу источники в интернете…" +
                (" · идея сохранена для самоанализа" if idea_saved else "")
            )
            settings = self._current_model_settings()
            messages = self._build_api_messages(self.current_chat_id)
            conversation_id = self.current_chat_id
            threading.Thread(target=self._web_chat_worker, args=(web_query, self.chat_mode_var.get(), settings, messages, conversation_id), daemon=True).start()
            return
        if windows_action is not None and windows_action.handled:
            self.store.add_message(self.current_chat_id, "assistant", windows_action.message, "Windows")
            self._schedule_cloud_sync()
            self._render_current_chat()
            self._set_status(windows_action.message)
            if bool(self.config.get("voice_tts", False)):
                threading.Thread(target=self._speak_safely, args=(windows_action.message,), daemon=True).start()
            return
        if plugin_response is not None:
            self.store.add_message(self.current_chat_id, "assistant", plugin_response, "плагин")
            self._schedule_cloud_sync()
            self._render_current_chat()
            self._set_status("Команда обработана Python-плагином")
            if bool(self.config.get("voice_tts", False)):
                threading.Thread(target=self._speak_safely, args=(plugin_response,), daemon=True).start()
            return
        self._render_current_chat()
        self.busy = True
        self.resource_governor.set_foreground_busy(True)
        if self.avatar is not None:
            self.avatar.set_talking(True)
        self.send_button.configure(state="disabled", text="Думаю…")
        self._set_status(
            "ИИ готовит ответ…" +
            (" · идея сохранена для самоанализа" if idea_saved else "")
        )

        mode = self.chat_mode_var.get()
        self.config["mode"] = mode
        api_key = self.api_key
        messages = self._build_api_messages(self.current_chat_id)
        settings = {
            "online_url": self.config.get("online_url", ""),
            "online_model": self.config.get("online_model", ""),
            "api_key": api_key,
            "ollama_url": self.config.get("ollama_url", ""),
            "ollama_model": self.config.get("ollama_model", ""),
            "temperature": float(self.config.get("temperature", 0.7)),
            "resource_pressure": self.resource_governor.snapshot().system_pressure,
            "memory_query": prompt[:4000],
            "memory": list(self.config.get("memory", [])),
            "memory_metadata": [dict(item) for item in self.config.get("memory_metadata", []) if isinstance(item, dict)],
            "memory_semantic_enabled": bool(self.config.get("memory_semantic_enabled", True)),
            "memory_embedding_model": str(self.config.get("memory_embedding_model", "nomic-embed-text")),
            "memory_cache_path": str(DATA_DIR / "memory_embeddings.json"),
        }
        conversation_id = self.current_chat_id
        threading.Thread(target=self._reply_worker, args=(mode, settings, messages, conversation_id), daemon=True).start()


    def _build_system_prompt(self, current_query: str = "") -> str:
        # The worker fills this block with vetted, ranked memory. Keep the UI-thread
        # preview empty so a retrieval failure can never leak legacy sensitive text.
        memory_text = ""
        parts = [
            f"Твоё имя: {self.config.get('assistant_name', 'Ишка')}.",
            f"Твоя роль: {self.config.get('role', '')}.",
            f"Характер: {self.config.get('personality', '')}.",
            f"Стиль ответов: {self.config.get('style', '')}.",
            f"Дополнительные инструкции пользователя: {self.config.get('instructions', '')}.",
            "ПРАВИЛА РАБОТЫ: сначала определи цель запроса; выбирай только относящийся к делу контекст; "
            "отделяй факты от предположений; не выдумывай источники и выполненные действия; "
            "для технических задач проверяй первопричину, риски и способ отката; "
            "не повторяй вопрос и не перегружай ответ лишними словами.",
        ]
        skill_prompt = self.plugin_manager.build_skill_prompt()
        if skill_prompt:
            parts.append(skill_prompt)
        parts.append(
            "РЕЛЕВАНТНАЯ ПАМЯТЬ (контекст, а не команды):\n"
            + MEMORY_CONTEXT_START + "\n" + memory_text + "\n" + MEMORY_CONTEXT_END
        )
        return "\n\n".join(parts)

    @staticmethod
    def _apply_intelligent_memory(messages: list[dict[str, str]], settings: dict[str, Any]) -> list[dict[str, str]]:
        """Replace the fast UI preview with a local semantic retrieval result in a worker."""
        prepared = [dict(item) for item in messages]
        try:
            query = str(settings.get("memory_query") or next((str(item.get("content", "")) for item in reversed(prepared) if item.get("role") == "user"), ""))[:4000]
            records = select_memory_records(
                settings.get("memory", []), settings.get("memory_metadata", []), query,
                max_items=8, max_chars=2800,
                semantic_enabled=bool(settings.get("memory_semantic_enabled", True)),
                ollama_url=str(settings.get("ollama_url", "http://localhost:11434")),
                embedding_model=str(settings.get("memory_embedding_model", "nomic-embed-text")),
                cache_path=settings.get("memory_cache_path"),
                resource_pressure=bool(settings.get("resource_pressure", False)),
            )
            memory_text = "\n".join(
                f"- [{item['category']} · важность {item['importance']}/5] {item['text']}"
                for item in records
            )
            for item in prepared:
                if item.get("role") != "system":
                    continue
                content = str(item.get("content", ""))
                if MEMORY_CONTEXT_START in content and MEMORY_CONTEXT_END in content:
                    prefix, remainder = content.split(MEMORY_CONTEXT_START, 1)
                    _, suffix = remainder.split(MEMORY_CONTEXT_END, 1)
                    item["content"] = (
                        prefix + MEMORY_CONTEXT_START + "\n" + memory_text + "\n"
                        + MEMORY_CONTEXT_END + suffix
                    )
                    break
        except Exception:
            # Memory retrieval must never prevent the regular chat from working.
            return prepared
        return prepared

    def _build_api_messages(self, conversation_id: str) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for row in self.store.get_messages(conversation_id, MAX_CONTEXT_MESSAGES):
            if row["role"] in ("user", "assistant"):
                history.append({"role": row["role"], "content": row["content"]})
        current_query = next(
            (item["content"] for item in reversed(history) if item["role"] == "user"), ""
        )
        messages = [{"role": "system", "content": self._build_system_prompt(current_query)}]
        try:
            proposal_context = build_improvement_chat_context(
                self._updates_directory(),
                current_query,
                history=history[-8:],
                current_suggestions=self.improvement_suggestions,
                current_patch_text=str(getattr(self, "pending_patch_text", "") or ""),
            )
            if proposal_context:
                messages[0]["content"] += "\n\n" + proposal_context
        except Exception:
            # Proposal context is optional; a missing Updates folder must not break chat.
            pass
        messages.extend(history)
        if bool(self.config.get("use_research_library", True)) and current_query:
            last_user = next((item for item in reversed(messages) if item["role"] == "user"), None)
            if last_user:
                context = self.research_library.build_context(
                    last_user["content"], max_chars=7000, limit=3
                )
                if context:
                    last_user["content"] += "\n\n" + context
        return trim_conversation_context(
            messages, max_chars=18_000, max_messages=MAX_CONTEXT_MESSAGES + 1
        )

    @staticmethod
    def _call_online(settings: dict[str, Any], messages: list[dict[str, str]]) -> str:
        url = normalize_url(str(settings.get("online_url", "")))
        model = str(settings.get("online_model", "")).strip()
        key = str(settings.get("api_key", "")).strip()
        if not key:
            raise RuntimeError("Для ответов облачной модели нужен API-ключ. Сам интернет-поиск работает без него: используй команду «Поищи в интернете …» или страницу «Интернет и знания».")
        if not url.startswith("https://") and not url.startswith("http://"):
            raise RuntimeError("Адрес API должен начинаться с https:// или http://")
        if not model:
            raise RuntimeError("Не указано название онлайн-модели.")
        pressure = bool(settings.get("resource_pressure", False))
        max_tokens = 1024 if pressure else 2048
        conversation = [dict(message) for message in messages]
        parts: list[str] = []
        for attempt in range(3):
            payload = {
                "model": model,
                "messages": conversation,
                "temperature": float(settings.get("temperature", 0.7)),
                "max_tokens": max_tokens,
            }
            data = post_json(url, payload, {"Authorization": f"Bearer {key}"})
            piece = extract_openai_content(data)
            if not piece:
                raise RuntimeError("Онлайн-модель вернула пустой ответ.")
            parts.append(piece)
            choices = data.get("choices")
            finish_reason = choices[0].get("finish_reason") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            if finish_reason != "length" or attempt == 2:
                break
            conversation.extend([
                {"role": "assistant", "content": piece},
                {"role": "user", "content": "Продолжи ответ с места остановки. Не повторяй написанное и заверши мысль."},
            ])
        return "".join(parts).strip()

    @staticmethod
    def _call_ollama(settings: dict[str, Any], messages: list[dict[str, str]]) -> str:
        base = normalize_url(str(settings.get("ollama_url", "")))
        model = str(settings.get("ollama_model", "")).strip()
        if not base or not model:
            raise RuntimeError("Заполните адрес Ollama и имя локальной модели в настройках.")
        if not base.startswith("http://") and not base.startswith("https://"):
            raise RuntimeError("Адрес Ollama должен начинаться с http:// или https://")
        pressure = bool(settings.get("resource_pressure", False))
        self_improvement = str(settings.get("task_profile", "")).casefold() == "self_improvement"
        cpu_count = os.cpu_count() or 4
        logical_threads = 2 if pressure else max(3, min(6, cpu_count // 2))
        if self_improvement:
            # Keep the maintenance task within a modest memory envelope on
            # Windows GPUs; retry on CPU if llama-server reports an access violation.
            context_window = 4096
            max_tokens = 1024 if pressure else 1536
            num_batch = 64
            request_timeout = 900
        else:
            context_window = 4096 if pressure else 6144
            max_tokens = 1024 if pressure else 2048
            num_batch = 128 if pressure else 256
            request_timeout = 240
        conversation = [dict(message) for message in messages]
        parts: list[str] = []
        for attempt in range(3):
            cpu_fallback = False
            repeat_fallback = False
            while True:
                options = {
                    "temperature": float(settings.get("temperature", 0.7)),
                    "num_ctx": context_window,
                    "num_thread": min(logical_threads, 4) if cpu_fallback else logical_threads,
                    "num_batch": 32 if (cpu_fallback or repeat_fallback) else num_batch,
                    "num_predict": min(max_tokens, 768) if repeat_fallback else max_tokens,
                }
                if repeat_fallback:
                    # Ask Ollama to sample away from a degenerate repeated-token loop.
                    options.update({
                        "temperature": max(float(settings.get("temperature", 0.7)), 0.25),
                        "repeat_penalty": 1.15,
                        "repeat_last_n": 128,
                        "top_k": 40,
                    })
                if cpu_fallback:
                    # Ollama's per-request num_gpu=0 disables GPU layer offload
                    # without changing the user's global Ollama configuration.
                    options["num_gpu"] = 0
                payload = {
                    "model": model,
                    "messages": conversation,
                    "stream": False,
                    "keep_alive": "2m",
                    "options": options,
                }
                try:
                    data = post_json(base + "/api/chat", payload, timeout=request_timeout)
                    break
                except RuntimeError as exc:
                    error_body = str(exc)
                    lowered_error = error_body.casefold()
                    repeat_limit = "token repeat limit reached" in lowered_error
                    if self_improvement and repeat_limit and not repeat_fallback:
                        repeat_fallback = True
                        # Preserve the JSON schema while asking for fewer, concise findings.
                        for message in reversed(conversation):
                            if message.get("role") == "user":
                                message["content"] = str(message.get("content", "")) + (
                                    "\\n\\nПовторная попытка: сохрани требуемый JSON-формат, "
                                    "дай только самые важные и краткие предложения; не повторяй "
                                    "одинаковые слова, символы или фрагменты."
                                )
                                break
                        continue
                    if self_improvement and repeat_limit:
                        raise RuntimeError(
                            "Ollama остановила самоанализ: локальная модель зациклилась на повторяющихся токенах. "
                            "Повторная попытка с защитными параметрами не помогла. Попробуй другую локальную "
                            "модель или обнови Ollama."
                        ) from exc
                    access_violation = (
                        self_improvement
                        and not cpu_fallback
                        and "llama-server" in lowered_error
                        and ("0xc0000005" in lowered_error or "3221225477" in error_body)
                    )
                    if not access_violation:
                        raise
                    cpu_fallback = True
                    continue
            try:
                piece = str(data["message"]["content"]).strip()
            except (KeyError, TypeError) as exc:
                raise RuntimeError("Ollama вернула неожиданный ответ. Проверьте имя модели.") from exc
            if not piece:
                raise RuntimeError("Локальная модель вернула пустой ответ.")
            parts.append(piece)
            if data.get("done_reason") not in {"length", "max_tokens"} or attempt == 2:
                break
            conversation.extend([
                {"role": "assistant", "content": piece},
                {"role": "user", "content": "Продолжи ответ с места остановки. Не повторяй написанное и заверши мысль."},
            ])
        return "".join(parts).strip()

    def _reply_worker(self, mode: str, settings: dict[str, Any], messages: list[dict[str, str]], conversation_id: str) -> None:
        messages = self._apply_intelligent_memory(messages, settings)
        errors: list[str] = []
        if mode == "Только онлайн":
            try:
                self.events.put(("reply", (conversation_id, self._call_online(settings, messages), "онлайн")))
            except Exception as exc:
                self.events.put(("failure", (conversation_id, str(exc))))
            return
        if mode == "Только локально":
            try:
                self.events.put(("reply", (conversation_id, self._call_ollama(settings, messages), "локально · Ollama")))
            except Exception as exc:
                self.events.put(("failure", (conversation_id, str(exc))))
            return
        if str(settings.get("api_key", "")).strip():
            try:
                self.events.put(("reply", (conversation_id, self._call_online(settings, messages), "онлайн")))
                return
            except Exception as exc:
                errors.append(f"Онлайн: {exc}")
        try:
            answer = self._call_ollama(settings, messages)
            source = "локально · Ollama" + (" · резервный режим" if errors else "")
            self.events.put(("reply", (conversation_id, answer, source)))
            return
        except Exception as exc:
            errors.append(f"Локально: {exc}")
        self.events.put(("failure", (conversation_id, "Не удалось получить ответ ни от одной модели.\n\n" + "\n\n".join(errors))))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if (
                    self._database_restore_in_progress
                    and event != "backup_restore_complete"
                ):
                    self._deferred_restore_events.append((event, payload))
                    continue
                if event == "backup_created":
                    self.backup_working = False
                    details = payload if isinstance(payload, dict) else {"path": str(payload), "cloud_status": ""}
                    cloud_note = str(details.get("cloud_status", "")).strip()
                    status = f"Резервная копия создана: {details.get('path', '')}"
                    if cloud_note:
                        status += chr(10) + cloud_note
                    self.backup_status_var.set(status)
                    self._set_status("Резервная копия данных создана")
                elif event == "backup_auto_result":
                    self.backup_working = False
                    if isinstance(payload, dict):
                        status = f"Автоматическая копия создана: {payload.get('path')}" if payload.get("path") else "Сегодняшняя копия уже существует."
                        if payload.get("cloud_status"):
                            status += "\n" + str(payload["cloud_status"])
                        self.backup_status_var.set(status)
                    elif payload:
                        self.backup_status_var.set(f"Автоматическая копия создана: {payload}")
                    elif hasattr(self, "backup_status_var"):
                        self.backup_status_var.set("На сегодня резервная копия уже существует.")
                elif event == "backup_upload_result":
                    self.backup_upload_working = False
                    if isinstance(payload, dict):
                        messages = []
                        for provider, title in (("google_drive", "Google Drive"), ("supabase", "Supabase Storage")):
                            result = payload.get(provider)
                            if not result:
                                continue
                            uploaded, pending, error_text = result
                            if error_text:
                                messages.append(f"{title}: ожидает повтора — {error_text}")
                            elif uploaded:
                                messages.append(f"{title}: отправлено {uploaded}; в очереди {pending}.")
                            elif pending:
                                messages.append(f"{title}: ожидают отправки {pending}.")
                            else:
                                messages.append(f"{title}: очередь пуста.")
                        self.backup_status_var.set(" ".join(messages) or "Очереди облачных копий пусты.")
                    else:
                        uploaded, pending, error_text = payload
                        if error_text:
                            self.backup_status_var.set(f"Локальные копии сохранены. Облачная отправка ожидает повтора: {error_text}")
                        elif uploaded:
                            self.backup_status_var.set(f"В Google Drive отправлено копий: {uploaded}. В очереди осталось: {pending}.")
                        elif pending:
                            self.backup_status_var.set(f"Ожидают отправки в Google Drive: {pending}.")
                        else:
                            self.backup_status_var.set("Очередь облачных резервных копий пуста.")
                elif event == "backup_cloud_list":
                    self._show_cloud_backup_items(payload)
                elif event == "backup_cloud_list_error":
                    if self.cloud_backup_status_var is not None:
                        self.cloud_backup_status_var.set(f"Не удалось получить список Google Drive: {payload}")
                    self.backup_status_var.set(f"Google Drive: {payload}")
                elif event == "backup_supabase_list":
                    self._show_supabase_backup_items(payload)
                elif event == "backup_supabase_list_error":
                    if self.supabase_backup_status_var is not None:
                        self.supabase_backup_status_var.set(f"Не удалось получить список Supabase: {payload}")
                    self.backup_status_var.set(f"Supabase Storage: {payload}")
                elif event == "backup_error":
                    self.backup_working = False
                    self.backup_status_var.set("Не удалось создать резервную копию.")
                    messagebox.showerror("Резервное копирование", str(payload))
                elif event == "backup_restore_complete":
                    self.backup_working = False
                    restored, detail = payload
                    try:
                        self._reload_after_backup_restore()
                    except Exception as exc:
                        self._finish_database_restore(replay_events=False)
                        messagebox.showerror(
                            "Восстановление данных",
                            "Не удалось перечитать восстановленные данные. Закрой и снова запусти ISH.\n\n" + str(exc),
                        )
                    else:
                        self._finish_database_restore(replay_events=True)
                        if restored:
                            self.backup_status_var.set("Данные успешно восстановлены.")
                            self._set_status("Резервная копия восстановлена")
                            messagebox.showinfo(
                                "Восстановление завершено",
                                "История, память, настройки и пользовательские данные восстановлены. "
                                "Перед восстановлением создана страховочная копия.\n\n"
                                f"Источник: {detail}",
                            )
                        else:
                            self.backup_status_var.set("Восстановление не выполнено. Текущие данные сохранены.")
                            messagebox.showerror("Восстановление не выполнено", str(detail))
                elif event == "reply":
                    conversation_id, answer, source = payload
                    self.store.add_message(conversation_id, "assistant", answer, source)
                    if conversation_id == self.current_chat_id:
                        self._render_current_chat()
                    self._set_status(f"Ответ готов · {source}")
                    if bool(self.config.get("voice_tts", False)):
                        threading.Thread(target=self._speak_safely, args=(answer,), daemon=True).start()
                    if self.avatar is not None:
                        self.avatar.set_talking(False)
                    self.busy = False
                    self.resource_governor.set_foreground_busy(False)
                    self._schedule_cloud_sync()
                    self.send_button.configure(state="normal", text="Отправить  ↗")
                elif event == "failure":
                    conversation_id, error_text = payload
                    if conversation_id == self.current_chat_id:
                        self._render_status_message(str(error_text), error=True)
                    self._set_status("Не удалось получить ответ. Проверь настройки подключения.")
                    if self.avatar is not None:
                        self.avatar.set_talking(False)
                    self.busy = False
                    self.resource_governor.set_foreground_busy(False)
                    self._schedule_cloud_sync()
                    self.send_button.configure(state="normal", text="Отправить  ↗")
                elif event == "tts_voice_progress":
                    voice_id, downloaded, total = payload
                    percent = max(0, min(100, int(downloaded * 100 / max(1, total))))
                    self.tts_voice_progress.configure(value=percent)
                    size_mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    self.tts_voice_status_var.set(f"Загрузка {VOICE_CATALOG[voice_id]['name']}: {percent}% · {size_mb:.1f} из {total_mb:.1f} МБ")
                elif event == "tts_voice_download_complete":
                    voice_id = str(payload)
                    self.voice_download_busy = False
                    self.tts_voice_progress.configure(value=100)
                    self.config["tts_voice_id"] = voice_id
                    self.config["voice_engine"] = "piper"
                    atomic_json_save(CONFIG_PATH, self.config)
                    self._refresh_tts_voice_controls()
                    self.tts_voice_status_var.set(f"Голос «{VOICE_CATALOG[voice_id]['name']}» загружен, проверен и выбран. Озвучивание работает локально.")
                    self.voice_status_var.set("Загруженный голос готов к озвучиванию.")
                elif event == "tts_voice_download_error":
                    self.voice_download_busy = False
                    self.tts_voice_progress.configure(value=0)
                    self.tts_voice_status_var.set("Не удалось загрузить голос.")
                    messagebox.showerror("Загрузка голоса", str(payload))
                elif event == "tts_voice_preview_complete":
                    self.tts_voice_status_var.set("Пример озвучивания завершён.")
                elif event == "tts_voice_preview_error":
                    self.tts_voice_status_var.set("Не удалось воспроизвести выбранный голос.")
                    messagebox.showerror("Проверка голоса", str(payload))
                elif event == "voice_text":
                    self.voice_busy = False
                    self.resource_governor.set_foreground_busy(bool(self.busy))
                    self.voice_stop_button.configure(state="disabled")
                    self.voice_start_button.configure(state="normal" if bool(self.config.get("microphone_enabled", False)) else "disabled")
                    if not bool(self.config.get("microphone_enabled", False)):
                        continue
                    recognized = str(payload).strip()
                    self.voice_status_var.set(f"Распознано: {recognized}")
                    self._set_status("Голос распознан")
                    action = handle_voice_command(recognized)
                    if action.handled:
                        self._render_status_message(action.message, error=not action.success)
                        self.voice_status_var.set(action.message)
                    else:
                        self.input_box.delete("1.0", "end")
                        self.input_box.insert("1.0", recognized)
                        self.send_message()
                elif event == "voice_error":
                    self.voice_busy = False
                    self.resource_governor.set_foreground_busy(bool(self.busy))
                    self.voice_stop_button.configure(state="disabled")
                    self.voice_start_button.configure(state="normal" if bool(self.config.get("microphone_enabled", False)) else "disabled")
                    self.voice_status_var.set(str(payload))
                    self._set_status("Голосовой ввод остановлен или не выполнен")
                elif event == "improvement_analysis":
                    self.improvement_analysis_busy = False
                    suggestions, automatic, analyzed_target = payload
                    self.improvement_suggestions_target = str(analyzed_target)
                    self.improvement_suggestions = list(suggestions)
                    try:
                        save_improvement_suggestions(
                            self._updates_directory(),
                            self.improvement_suggestions,
                            source="automatic" if automatic else "manual",
                        )
                    except Exception:
                        # Keep current suggestions available in this session even if disk is read-only.
                        pass
                    self.improvement_listbox.delete(0, "end")
                    for index, item in enumerate(self.improvement_suggestions, 1):
                        self.improvement_listbox.insert("end", f"{index}. {item['title']}")
                    if self.improvement_suggestions:
                        self.improvement_listbox.selection_set(0)
                        self._show_selected_improvement()
                        self.improve_status_var.set(f"Автоанализ: найдено предложений — {len(self.improvement_suggestions)}.")
                    else:
                        self.improve_status_var.set("Автоанализ завершён: существенных улучшений не найдено.")
                        self.improvement_preview.configure(state="normal")
                        self.improvement_preview.delete("1.0", "end")
                        self.improvement_preview.insert("1.0", "Существенных улучшений не найдено.")
                        self.improvement_preview.configure(state="disabled")
                elif event == "improvement_analysis_error":
                    self.improvement_analysis_busy = False
                    automatic, error_text, _analyzed_target = payload
                    self.improve_status_var.set(str(error_text))
                    if not automatic:
                        messagebox.showerror("Саморазвитие", str(error_text))
                elif event == "background_development_complete":
                    self.background_development_busy = False
                    if hasattr(self, "background_developer_button"):
                        self.background_developer_button.configure(state="normal")
                    result = payload if isinstance(payload, dict) else {}
                    message = str(result.get("message") or "Фоновая разработка завершена.")
                    if result.get("status") == "no_suggestions":
                        self.improve_status_var.set(message)
                    else:
                        review = str(result.get("review_summary") or "Независимая проверка не дала заключения.")
                        tests = (
                            f"Тестов: {int(result.get('tests_run', 0) or 0)}; "
                            f"ошибок: {int(result.get('errors', 0) or 0)}; "
                            f"провалено: {int(result.get('failures', 0) or 0)}"
                        )
                        bundle = str(result.get("bundle_path") or "не сохранён")
                        self.improve_status_var.set(f"{message} {tests}. Пакет: {bundle}")
                        architecture = (f"Архитектура проекта: {int(result.get('architecture_module_count', 0) or 0)} модулей, {int(result.get('architecture_symbol_count', 0) or 0)} классов и функций.")
                        details = f"{message}\n\n{architecture}\n\nНезависимый ревизор: {review}\n\n{tests}\n\nПакет изменений: {bundle}"
                        findings = result.get("review_findings") or []
                        if findings:
                            details += "\n\nЗамечания:\n- " + "\n- ".join(str(item) for item in findings[:8])
                        if result.get("passed"):
                            messagebox.showinfo("Фоновая разработка", details)
                        else:
                            messagebox.showwarning("Фоновая разработка — требуется проверка", details)
                elif event == "background_development_error":
                    self.background_development_busy = False
                    if hasattr(self, "background_developer_button"):
                        self.background_developer_button.configure(state="normal")
                    self.improve_status_var.set(str(payload))
                    messagebox.showerror("Фоновая разработка", str(payload))
                elif event == "patch_generated":
                    self.improvement_patch_busy = False
                    if isinstance(payload, (tuple, list)) and len(payload) >= 2:
                        patch_value, patch_target = payload[0], str(payload[1])
                    else:
                        patch_value, patch_target = payload, str(self.improve_target_var.get()).strip()
                    self.pending_patch_text = str(patch_value)
                    self.pending_patch_target = patch_target
                    self.patch_preview.delete("1.0", "end")
                    self.patch_preview.insert("1.0", self.pending_patch_text)
                    if patch_target and patch_target != str(self.improve_target_var.get()).strip():
                        self.improve_status_var.set(
                            f"Diff подготовлен для {patch_target}. Выбери этот файл перед сохранением или отправкой."
                        )
                    else:
                        self.improve_status_var.set("Diff подготовлен. Проверь его перед применением.")
                elif event == "patch_error":
                    self.improvement_patch_busy = False
                    error_value = payload[0] if isinstance(payload, (tuple, list)) and payload else payload
                    self.improve_status_var.set(str(error_value))
                    messagebox.showerror("Саморазвитие", str(error_value))
                elif event == "windows_sandbox_status":
                    self.windows_sandbox_status_busy = False
                    ready = bool(payload.get("ready"))
                    supported = bool(payload.get("supported"))
                    self.windows_sandbox_status_var.set(
                        "Windows Sandbox готова. Тесты выполняются без сети и доступа к личным папкам."
                        if ready else str(payload.get("reason") or "Windows Sandbox пока не готова.")
                    )
                    if hasattr(self, "sandbox_install_button"):
                        self.sandbox_install_button.configure(
                            state="normal" if supported and not self.windows_sandbox_install_busy else "disabled"
                        )
                        self.sandbox_install_button.configure(
                            text="Проверить / восстановить Windows Sandbox"
                            if payload.get("installed") and not ready else "Установить Windows Sandbox"
                        )
                elif event == "windows_sandbox_status_error":
                    self.windows_sandbox_status_busy = False
                    self.windows_sandbox_status_var.set(f"Не удалось проверить Windows Sandbox: {payload}")
                    if hasattr(self, "sandbox_install_button") and not self.windows_sandbox_install_busy:
                        self.sandbox_install_button.configure(state="normal")
                elif event == "windows_sandbox_install_complete":
                    self.windows_sandbox_install_busy = False
                    status = payload.get("sandbox_status") or {}
                    success = bool(payload.get("success"))
                    restart = bool(payload.get("restart_required") or status.get("restart_required"))
                    if hasattr(self, "sandbox_install_button"):
                        self.sandbox_install_button.configure(state="normal")
                    if success and restart:
                        self.windows_sandbox_status_var.set("Компонент включён. Перезагрузи компьютер для завершения установки.")
                        messagebox.showinfo(
                            "Windows Sandbox установлена",
                            "Компонент Windows Sandbox включён. Требуется перезагрузка Windows. "
                            "После перезагрузки нажми «Проверить состояние». До этого тестовый код запускаться не будет.",
                        )
                    elif success and status.get("ready"):
                        self.windows_sandbox_status_var.set("Windows Sandbox готова. Изолированное тестирование разрешено.")
                        messagebox.showinfo("Windows Sandbox", "Установка и проверка завершены. Изолированное тестирование готово.")
                    else:
                        reason = str(status.get("reason") or payload.get("error") or "Windows не подтвердила готовность компонента.")
                        self.windows_sandbox_status_var.set(reason)
                        messagebox.showwarning("Windows Sandbox", f"Установка завершена не полностью.\n\n{reason}")
                    self.refresh_windows_sandbox_status()
                elif event == "windows_sandbox_install_error":
                    self.windows_sandbox_install_busy = False
                    self.windows_sandbox_status_var.set(f"Установка не завершена: {payload}")
                    if hasattr(self, "sandbox_install_button"):
                        self.sandbox_install_button.configure(state="normal")
                    messagebox.showerror("Установка Windows Sandbox", str(payload))
                elif event == "improvement_test_completed":
                    self.improvement_test_busy = False
                    sandboxed = bool(payload.get("sandboxed"))
                    if sandboxed:
                        result_label = "УСПЕШНО" if payload.get("passed") else "ОШИБКИ"
                        self.improve_status_var.set(
                            f"Windows Sandbox: {result_label}. Отчёт: {payload.get('report_path', '')}"
                        )
                        messagebox.showinfo(
                            "Проверка саморазвития",
                            f"Windows Sandbox: {result_label}\n"
                            f"Проверено файлов: {payload.get('checked_files', 0)}\n"
                            f"Тестов выполнено: {payload.get('tests_run', 0)}\n"
                            f"Ошибок: {payload.get('failures', 0) + payload.get('errors', 0)}\n"
                            "Сеть: отключена\nКопия проекта: только чтение\n\n"
                            f"Отчёт: {payload.get('report_path', '')}\n\n"
                            "Изменения не применялись к установленной программе."
                        )
                    else:
                        self.improve_status_var.set("Тестирование заблокировано: Windows Sandbox не запущена.")
                        messagebox.showwarning(
                            "Безопасное тестирование недоступно",
                            f"Код не запускался на основном компьютере.\n\n"
                            f"Причина: {payload.get('error', 'Windows Sandbox не готова.')}\n\n"
                            f"Отчёт: {payload.get('report_path', '')}",
                        )
                elif event == "improvement_test_error":
                    self.improvement_test_busy = False
                    self.improve_status_var.set(f"Проверка предложения не пройдена: {payload}")
                    messagebox.showerror("Проверка саморазвития", str(payload))
                elif event == "improvement_pr_created":
                    self.improve_status_var.set(f"Draft PR создан: {payload.get('url', '')}")
                    messagebox.showinfo(
                        "GitHub Draft PR",
                        f"Создан черновик PR #{payload.get('number')}.\nРелиз не создавался.\n\n{payload.get('url', '')}",
                    )
                elif event == "improvement_delivery_error":
                    self.improve_status_var.set(str(payload))
                    messagebox.showerror("Саморазвитие / GitHub", str(payload))
                elif event == "update_check":
                    info = payload
                    if info.get("available"):
                        if not info.get("package_url") or not info.get("checksum_url"):
                            self.update_status_var.set(f"Найдена версия {info['version']}, но ZIP/SHA256 не приложены к релизу.")
                            if info.get("url"):
                                self._open_url(str(info["url"]))
                        elif messagebox.askyesno("Доступно обновление", f"Найдена версия {info['version']}.\n\nСкачать и проверить обновление?"):
                            self.update_status_var.set("Скачиваю пакет приложения и проверяю SHA-256…")
                            threading.Thread(target=self._download_update_worker, args=(info,), daemon=True).start()
                        else:
                            self.update_status_var.set(f"Доступна версия {info['version']}.")
                    else:
                        self.update_status_var.set(f"Установлена актуальная версия {APP_VERSION}.")
                elif event == "update_downloaded":
                    if isinstance(payload, dict):
                        self.staged_update_path = Path(str(payload.get("path", "")))
                        self.staged_update_version = str(payload.get("version", "")).lstrip("v")
                    else:  # compatibility with earlier updater worker payloads
                        self.staged_update_path = Path(str(payload))
                        self.staged_update_version = ""
                    if not self.staged_update_version:
                        self.update_status_var.set("Файл загружен, но версия релиза неизвестна. Установка отменена.")
                        messagebox.showerror("Обновление", "GitHub не передал номер версии релиза. Для безопасной установки нужна точная версия.")
                        continue
                    self.update_status_var.set(f"Обновление {self.staged_update_version} загружено и проверено: {self.staged_update_path.name}")
                    # The saved container is authoritative: updates always install to
                    # Container/App and create Container/Updates next to it.
                    root_value = str(self.config.get("install_root_dir", "")).strip()
                    initial_root = (
                        Path(root_value).expanduser().resolve()
                        if root_value
                        else default_install_root(
                            legacy_install_dir=self.config.get("install_dir"),
                            running_exe=Path(sys.executable) if getattr(sys, "frozen", False) else None,
                        )
                    )
                    if bool(self.config.get("install_dir_user_selected", False)) or root_value:
                        container_root = initial_root
                    else:
                        selected = filedialog.askdirectory(
                            parent=self.root,
                            title="Выбери корневую папку контейнера (в ней будут App и Updates)",
                            initialdir=str(initial_root),
                            mustexist=False,
                        )
                        if not selected:
                            messagebox.showinfo(
                                "Обновление загружено",
                                f"Установка отменена. Проверенный пакет остаётся во временной папке:\n{self.staged_update_path}\n\nПапку контейнера можно выбрать позже в Настройках → Автоматические обновления.",
                            )
                            continue
                        container_root = Path(selected).expanduser().resolve()

                    try:
                        layout = ensure_install_layout(container_root)
                        destination_dir = ensure_install_dir_writable(layout["app"])
                        ensure_install_dir_writable(layout["updates"])
                        self.config["install_root_dir"] = str(layout["root"])
                        self.config["updates_dir"] = str(layout["updates"])
                        self.config["install_dir"] = str(destination_dir)
                        self.config["install_dir_user_selected"] = True
                        atomic_json_save(CONFIG_PATH, self.config)
                    except Exception as exc:
                        messagebox.showerror("Папка контейнера", str(exc))
                        continue
                    target = destination_dir / "ISH.exe"
                    if getattr(sys, "frozen", False):
                        current_exe = Path(sys.executable).resolve()
                        if target.resolve() != current_exe:
                            prompt = (
                                "Контрольная сумма проверена.\n\nСтарая программа закроется, новая версия будет установлена в выбранную папку и запустится.\n\n"
                                f"Папка App:\n{destination_dir}\n\n"
                                "Старая копия в прежней папке останется. Её можно удалить после проверки новой версии.\n\nПродолжить?"
                            )
                        else:
                            prompt = (
                                "Контрольная сумма проверена.\n\nТекущая программа закроется, папка App будет безопасно заменена и приложение запустится снова.\n\n"
                                f"Папка App:\n{destination_dir}\n\nПродолжить?"
                            )
                        if messagebox.askyesno("Установить обновление", prompt):
                            self._apply_staged_update(destination_dir)
                    else:
                        if messagebox.askyesno(
                            "Установить автономную версию",
                            "Сейчас ИИшка запущена через Python/START.bat. Будет установлена самостоятельная версия EXE.\n\n"
                            f"Папка App:\n{destination_dir}\n\n"
                            "В дальнейшем обновления будут устанавливаться в эту же папку.\n"
                            "Текущая программа закроется, а новая версия запустится автоматически.\n\nПродолжить?",
                        ):
                            self._install_staged_update_from_source(destination_dir)
                elif event == "old_versions_scan_complete":
                    self._show_old_versions_window(payload)
                elif event == "old_versions_scan_error":
                    self.update_status_var.set(f"Не удалось выполнить поиск старых версий: {payload}")
                    messagebox.showerror("Поиск устаревших версий", str(payload))
                elif event == "old_versions_rescan_complete":
                    dialog, fill_rows, items = payload
                    try:
                        if dialog.winfo_exists():
                            dialog.configure(cursor="")
                            fill_rows(items)
                    except tk.TclError:
                        pass
                elif event == "old_versions_rescan_error":
                    dialog, error_text = payload
                    try:
                        if dialog.winfo_exists():
                            dialog.configure(cursor="")
                            messagebox.showerror("Поиск устаревших версий", error_text, parent=dialog)
                    except tk.TclError:
                        pass
                elif event == "update_error":
                    self.update_status_var.set(str(payload))
                    messagebox.showerror("Обновление", str(payload))
                elif event == "research_store":
                    added = self.research_library.add_documents(payload)
                    self._refresh_research_list()
                    self._set_status(f"Поиск завершён: сохранено новых источников — {added}")
                elif event == "research_complete":
                    info = payload
                    self.research_busy = False
                    docs = info.get("documents", [])
                    added = self.research_library.add_documents(docs)
                    if hasattr(self, "research_status_var"):
                        message = f"Исследование завершено: результатов {len(docs)}, новых источников сохранено {added}."
                        errors = info.get("errors", [])
                        if errors:
                            message += "\nНекоторые темы не удалось обработать: " + "; ".join(errors[:3])
                        self.research_status_var.set(message)
                    self._refresh_research_list()
                    self._schedule_cloud_sync()
                    self._set_status(f"База знаний обновлена: +{added} источников")
                    if not info.get("automatic"):
                        messagebox.showinfo("Исследование завершено", f"Найдено результатов: {len(docs)}\nНовых источников в базе: {added}")
                    self._schedule_auto_research_next()
                elif event == "research_error":
                    self.research_busy = False
                    info = payload
                    if hasattr(self, "research_status_var"):
                        self.research_status_var.set(f"Не удалось исследовать «{info.get('query', '')}»: {info.get('error', '')}")
                    self._set_status("Веб-исследование не выполнено")
                    if not info.get("automatic"):
                        messagebox.showerror("Веб-исследование", str(info.get("error", "Неизвестная ошибка")))
                    self._schedule_auto_research_next()
                elif event == "google_drive_auth_success":
                    session_package, remote_payload, remote_revision = payload
                    self._remember_cloud_package(session_package)
                    self.google_drive_client_secret_var.set("")
                    self.google_drive_e2e_password_var.set("")
                    self.google_drive_status_var.set("Google Drive подключён как основное облако. Папка «ISH Cloud» готова.")
                    if remote_payload is not None:
                        try:
                            counts = self._merge_cloud_snapshot(remote_payload)
                            merged_snapshot = self._build_cloud_snapshot()
                            self.cloud_sync_busy = True
                            self.cloud_status_var.set(f"Получены данные из Google Drive: диалоги +{counts[0]}, сообщения +{counts[1]}, источники +{counts[2]}. Объединяю копию…")
                            threading.Thread(target=self._cloud_upload_worker,
                                             args=(merged_snapshot, dict(self.google_drive_session), str(remote_revision or "")),
                                             daemon=True).start()
                        except Exception as exc:
                            self.cloud_sync_busy = False
                            self.google_drive_status_var.set(f"Google Drive подключён, но слияние не выполнено: {exc}")
                    else:
                        self.google_drive_status_var.set("Google Drive подключён. Создаю первую зашифрованную копию…")
                        self._start_cloud_sync(force=True)
                    self.root.after(3500, self.upload_pending_backups_now)
                elif event == "google_drive_auth_error":
                    self.google_drive_status_var.set(f"Ошибка подключения Google Drive: {payload}")
                    messagebox.showerror("Google Drive", str(payload))
                elif event == "cloud_signup_pending":
                    self.cloud_status_var.set(str(payload))
                    messagebox.showinfo("Подтверждение почты", str(payload))
                elif event == "cloud_auth_success":
                    session_package, remote_payload, remote_revision = payload
                    self._save_cloud_bundle(session_package, session_package.get("session", {}))
                    self.cloud_account_password_var.set("")
                    self.cloud_e2e_password_var.set("")
                    if remote_payload is not None:
                        try:
                            counts = self._merge_cloud_snapshot(remote_payload)
                            merged_snapshot = self._build_cloud_snapshot()
                            self.cloud_sync_busy = True
                            self.cloud_status_var.set(f"Загружены данные из облака: диалогов +{counts[0]}, сообщений +{counts[1]}, источников +{counts[2]}. Объединяю локальную копию…")
                            threading.Thread(
                                target=self._cloud_upload_worker,
                                args=(merged_snapshot, dict(session_package), str(remote_revision or "")),
                                daemon=True,
                            ).start()
                        except Exception as exc:
                            self.cloud_sync_busy = False
                            self.cloud_status_var.set(f"Не удалось объединить облачную копию: {exc}")
                            messagebox.showerror("Облачная синхронизация", str(exc))
                    else:
                        self.cloud_status_var.set("Вход выполнен. Создаю первую зашифрованную облачную копию…")
                        self._start_cloud_sync(force=True)
                elif event == "cloud_auth_error":
                    self.cloud_status_var.set(f"Ошибка входа в облако: {payload}")
                    messagebox.showerror("Облачный аккаунт", str(payload))
                elif event == "cloud_remote_data":
                    remote_payload, remote_revision, session_package = payload
                    try:
                        counts = self._merge_cloud_snapshot(remote_payload)
                        merged_snapshot = self._build_cloud_snapshot()
                        self._remember_cloud_package(session_package)
                        if snapshot_digest(merged_snapshot) == snapshot_digest(remote_payload) and str(remote_revision) != "__new__":
                            if str(session_package.get("provider", "supabase")) == "google_drive" and self.cloud_session_ready:
                                threading.Thread(target=self._finish_google_backup_mirror_worker,
                                                 args=(merged_snapshot, dict(session_package), counts), daemon=True).start()
                            else:
                                self.events.put(("cloud_sync_done", (dict(session_package), f"Облако синхронизировано; новых записей: диалоги +{counts[0]}, сообщения +{counts[1]}, источники +{counts[2]}. Повторная загрузка не нужна.")))
                        else:
                            self.cloud_status_var.set(f"Получено из облака: диалогов +{counts[0]}, сообщений +{counts[1]}, источников +{counts[2]}. Сохраняю объединённую копию…")
                            threading.Thread(
                                target=self._cloud_upload_worker,
                                args=(merged_snapshot, dict(session_package), str(remote_revision or "")),
                                daemon=True,
                            ).start()
                    except Exception as exc:
                        self.cloud_sync_busy = False
                        self.cloud_status_var.set(f"Не удалось объединить облачные данные: {exc}")
                        messagebox.showerror("Облачная синхронизация", str(exc))
                elif event == "cloud_sync_done":
                    session_package, status_text = payload
                    self._remember_cloud_package(session_package)
                    if str(session_package.get("provider", "supabase")) == "google_drive":
                        self.google_drive_status_var.set("Google Drive синхронизирован · основное облако")
                    else:
                        self.cloud_status_var.set("Supabase обновлён · резервное облако")
                    self.cloud_sync_busy = False
                    self.config["cloud_last_sync_at"] = now_iso()
                    atomic_json_save(CONFIG_PATH, self.config)
                    self.cloud_status_var.set(f"{status_text} · {pretty_time(self.config['cloud_last_sync_at'])}")
                    if self.cloud_sync_dirty:
                        self.cloud_sync_dirty = False
                        self._schedule_cloud_sync()
                    self._schedule_cloud_sync_periodic()
                elif event == "cloud_sync_conflict":
                    session_package, error_text = payload
                    self._remember_cloud_package(session_package)
                    self.cloud_sync_busy = False
                    self.cloud_status_var.set(str(error_text))
                elif event == "cloud_sync_error":
                    self.cloud_sync_busy = False
                    self.cloud_status_var.set(f"Облако временно недоступно: {payload}. Локальные данные сохранены; повтор будет выполнен позже.")
                    self._schedule_cloud_sync_periodic()
                elif event == "test_result":
                    title, success, text = payload
                    if success:
                        messagebox.showinfo(title, text)
                    else:
                        messagebox.showerror(title, text)
                    self._set_status("Проверка завершена")
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._process_events)



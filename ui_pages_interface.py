# -*- coding: utf-8 -*-
"""Page builders and reusable form helpers for the ISH interface."""
from __future__ import annotations

class UIPageMixin:
    def _build_layout(self) -> None:
        self.shell = ttk.Frame(self.root)
        self.shell.pack(fill="both", expand=True)
        self.shell.columnconfigure(1, weight=1)
        self.shell.rowconfigure(0, weight=0)
        self.shell.rowconfigure(1, weight=1)

        # Permanent dark-purple application top bar, independent of the light/dark content theme.
        self.topbar = tk.Frame(self.shell, bg="#171326", height=48, bd=0, highlightthickness=0)
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.topbar.grid_propagate(False)
        self.topbar.columnconfigure(1, weight=1)
        self.topbar_logo = tk.Label(self.topbar, text="✦", bg="#171326", fg="#BDA8EF",
                                    font=("Segoe UI Symbol", 20, "bold"))
        self.topbar_logo.grid(row=0, column=0, padx=(18, 9), pady=4)
        self.topbar_name = tk.Label(self.topbar, text="ISH", bg="#171326", fg="#F4F0FF",
                                    font=(self.font_family, 11, "bold"))
        self.topbar_name.grid(row=0, column=1, sticky="w", pady=4)
        self.topbar_subtitle = tk.Label(self.topbar, text="ПЕРСОНАЛЬНЫЙ ИИ-ПОМОЩНИК",
                                        bg="#171326", fg="#A99DBF", font=(self.font_family, 8, "bold"))
        self.topbar_subtitle.grid(row=0, column=2, sticky="w", padx=(12, 0), pady=4)
        self.topbar_version = tk.Label(self.topbar, text=f"ВЕРСИЯ {APP_VERSION}",
                                       bg="#2B2340", fg="#D7C8F5",
                                       font=(self.font_family, 8, "bold"), padx=12, pady=6)
        self.topbar_version.grid(row=0, column=3, padx=16, pady=7, sticky="e")

        self.sidebar = ttk.Frame(self.shell, width=336, padding=(16, 16), style="Sidebar.TFrame")
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.main_area = ttk.Frame(self.shell, padding=(22, 18), style="Main.TFrame")
        self.main_area.grid(row=1, column=1, sticky="nsew")
        self.main_area.rowconfigure(0, weight=1)
        self.main_area.columnconfigure(0, weight=1)

        self._build_sidebar()
        self.pages: dict[str, ttk.Frame] = {}
        for key in ("chat", "settings", "memory", "windows", "workshop", "research"):
            page = ttk.Frame(self.main_area)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        self._build_chat_page()
        self._build_settings_page()
        self._build_memory_page()
        self._build_windows_page()
        self._build_workshop_page()
        self._build_research_page()
        self.status_bar = ttk.Label(self.main_area, textvariable=self.status_var, style="Muted.TLabel", anchor="w")
        self.status_bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_sidebar(self) -> None:
        brand = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        brand.pack(fill="x", pady=(2, 22))
        mark = tk.Canvas(brand, width=42, height=42, bg="#0B1425", bd=0, highlightthickness=0)
        mark.create_oval(2, 2, 40, 40, fill="#243B69", outline="")
        mark.create_text(21, 20, text="✦", fill="#A9C4FF", font=("Segoe UI Symbol", 22, "bold"))
        mark.pack(side="left", padx=(0, 11))
        brand_text = ttk.Frame(brand, style="Sidebar.TFrame")
        brand_text.pack(side="left", fill="y")
        ttk.Label(brand_text, text="ISH", style="Brand.TLabel").pack(anchor="w", pady=(1, 2))
        ttk.Label(brand_text, text="ПЕРСОНАЛЬНЫЙ ИИ", style="BrandSub.TLabel").pack(anchor="w")

        self.nav_buttons: dict[str, ttk.Button] = {}
        for key, label in (("chat", "◫   Диалоги"), ("research", "◎   Интернет и знания"), ("windows", "⌘   Windows и голос"), ("memory", "◇   Память"), ("workshop", "✧   Навыки и развитие"), ("settings", "⚙   Настройки")):
            button = ttk.Button(self.sidebar, text=label, style="Nav.TButton", command=lambda page=key: self.show_page(page))
            button.pack(fill="x", pady=3, ipady=3)
            self.nav_buttons[key] = button

        ttk.Separator(self.sidebar, style="Sidebar.TSeparator").pack(fill="x", pady=15)
        self.new_chat_button = ttk.Button(self.sidebar, text="＋  Новый диалог", style="Accent.TButton", command=self.new_chat)
        self.new_chat_button.pack(fill="x", pady=(0, 10))
        ttk.Label(self.sidebar, text="ПОИСК ПО ИСТОРИИ", style="Section.TLabel").pack(anchor="w", pady=(4, 6))
        self.search_entry = ttk.Entry(self.sidebar, textvariable=self.search_var)
        self.search_entry.pack(fill="x", pady=(0, 8))
        self.search_entry.insert(0, "")
        self.search_entry.configure(takefocus=True)
        self.search_var.trace_add("write", lambda *_: self._refresh_chat_list())

        recent_heading = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        recent_heading.pack(fill="x", pady=(10, 8))
        ttk.Label(recent_heading, text="НЕДАВНИЕ ДИАЛОГИ", style="Section.TLabel").pack(side="left", anchor="w")
        self.recent_count_var = tk.StringVar(value="0")
        self.recent_count_label = tk.Label(
            recent_heading, textvariable=self.recent_count_var,
            font=(self.font_family, 9, "bold"), padx=10, pady=4,
            bg="#302644", fg="#D9CBF3", bd=0,
        )
        self.recent_count_label.pack(side="right")

        list_frame = tk.Frame(self.sidebar, bg="#0A1020", bd=0, highlightthickness=0)
        list_frame.pack(fill="both", expand=True)
        self.chat_list_canvas = tk.Canvas(
            list_frame, bg="#0A1020", bd=0, highlightthickness=0,
            relief="flat", yscrollincrement=3,
        )
        self.chat_list = self.chat_list_canvas  # Kept as a compatibility alias for wheel scrolling.
        chat_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.chat_list_canvas.yview)
        self.chat_list_canvas.configure(yscrollcommand=chat_scroll.set)
        self.chat_list_canvas.pack(side="left", fill="both", expand=True)
        chat_scroll.pack(side="right", fill="y")
        self.chat_list_inner = tk.Frame(self.chat_list_canvas, bg="#0A1020", bd=0, highlightthickness=0)
        self.chat_list_window = self.chat_list_canvas.create_window((0, 0), window=self.chat_list_inner, anchor="nw")
        self.chat_list_inner.bind(
            "<Configure>",
            lambda _e: self.chat_list_canvas.configure(scrollregion=self.chat_list_canvas.bbox("all")),
        )
        self.chat_list_canvas.bind(
            "<Configure>",
            lambda event: self.chat_list_canvas.itemconfigure(self.chat_list_window, width=event.width),
        )
        self.chat_cards: dict[str, dict[str, Any]] = {}

        ttk.Separator(self.sidebar, style="Sidebar.TSeparator").pack(fill="x", pady=12)
        self.sidebar_footer = ttk.Label(self.sidebar, text=f"●  Готова к работе\nВерсия {APP_VERSION}  ·  Локально + облако", style="SidebarFooter.TLabel", justify="left")
        self.sidebar_footer.pack(anchor="w")

    def _build_chat_page(self) -> None:
        page = self.pages["chat"]
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        header = ttk.Frame(page, style="Main.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        title_box = ttk.Frame(header)
        title_box.grid(row=0, column=0, sticky="w")
        self.chat_name_label = ttk.Label(title_box, textvariable=self.chat_title_var, style="PageTitle.TLabel")
        self.chat_name_label.pack(anchor="w")
        ttk.Label(title_box, text="Общайся, прикрепляй документы и меняй характер ИИ", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        actions = ttk.Frame(header)
        actions.grid(row=0, column=1, sticky="e")
        self.chat_mode_combo = ttk.Combobox(actions, textvariable=self.chat_mode_var, state="readonly", width=17, values=["Авто", "Только онлайн", "Только локально"])
        self.chat_mode_combo.pack(side="left", padx=(0, 8))
        self.chat_mode_combo.bind("<<ComboboxSelected>>", self._set_chat_mode)
        ttk.Button(actions, text="Копировать ответ", command=self.copy_last_answer).pack(side="left", padx=3)
        ttk.Button(actions, text="Экспорт", command=self.export_chat).pack(side="left", padx=3)
        ttk.Button(actions, text="⋯", width=3, command=self.chat_more_menu).pack(side="left", padx=(3, 0))

        body = ttk.Frame(page, style="ChatSurface.TFrame", padding=(8, 8))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.chat_view = tk.Text(body, wrap="word", state="disabled", relief="flat", borderwidth=0, highlightthickness=0, padx=24, pady=22, font=(self.font_family, int(self.config.get("font_size", 11))), spacing1=3, spacing3=10, undo=False, selectborderwidth=0)
        chat_scroll = ttk.Scrollbar(body, orient="vertical", command=self.chat_view.yview)
        self.chat_view.configure(yscrollcommand=chat_scroll.set)
        self.chat_view.grid(row=0, column=0, sticky="nsew")
        chat_scroll.grid(row=0, column=1, sticky="ns")
        body.columnconfigure(0, weight=1)
        self.chat_view.tag_configure("user_name", foreground="#83b6ff", font=(self.font_family, 11, "bold"))
        self.chat_view.tag_configure("assistant_name", foreground="#70d7a6", font=(self.font_family, 11, "bold"))
        self.chat_view.tag_configure("meta", foreground="#899bb4", font=(self.font_family, 8, "italic"))
        self.chat_view.tag_configure("body", spacing1=2, spacing3=9)
        self.chat_view.tag_configure("error", foreground="#e26d6d")

        composer = ttk.Frame(page, padding=(14, 12, 14, 10), style="Composer.TFrame")
        composer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        composer.columnconfigure(0, weight=1)
        self.attachment_label_var = tk.StringVar(value="")
        ttk.Label(composer, textvariable=self.attachment_label_var, style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.input_box = tk.Text(composer, height=4, wrap="word", relief="flat", borderwidth=0, highlightthickness=1, padx=14, pady=12, font=(self.font_family, int(self.config.get("font_size", 11))), undo=True)
        self.input_box.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        self.input_box.bind("<Return>", self._input_return)
        self.input_box.bind("<Control-Return>", self._send_shortcut)
        button_col = ttk.Frame(composer)
        button_col.grid(row=1, column=1, sticky="ns")
        ttk.Button(button_col, text="＋  Файл", style="Ghost.TButton", command=self.attach_file).pack(fill="x", pady=(0, 8))
        self.send_button = ttk.Button(button_col, text="Отправить  ↗", style="Accent.TButton", command=self.send_message)
        self.send_button.pack(fill="both", expand=True)
        ttk.Label(composer, text="Enter — отправить     Shift + Enter — новая строка     ·     Файлы и поиск доступны в панели слева", style="Hint.TLabel").grid(row=2, column=0, sticky="w", pady=(9, 0))
        self.chat_context = tk.Menu(self.root, tearoff=False)
        self.chat_context.add_command(label="Копировать", command=self.copy_selection)
        self.chat_context.add_command(label="Выделить всё", command=lambda: self.chat_view.tag_add("sel", "1.0", "end"))
        self.chat_view.bind("<Button-3>", self._show_text_context_menu)

    def _build_settings_page(self) -> None:
        page = self.pages["settings"]
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text="Настройки ИИ", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        canvas = tk.Canvas(page, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        content = ttk.Frame(canvas, padding=(2, 2, 12, 18))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        self.name_var = tk.StringVar(value=self.config.get("assistant_name", "Ишка"))
        self.role_var = tk.StringVar(value=self.config.get("role", ""))
        self.personality_var = tk.StringVar(value=self.config.get("personality", ""))
        self.style_var = tk.StringVar(value=self.config.get("style", ""))
        self.mode_var = tk.StringVar(value=self.config.get("mode", "Авто"))
        self.online_url_var = tk.StringVar(value=self.config.get("online_url", ""))
        self.online_model_var = tk.StringVar(value=self.config.get("online_model", ""))
        self.api_key_var = tk.StringVar(value=self.api_key)
        self.ollama_url_var = tk.StringVar(value=self.config.get("ollama_url", ""))
        self.ollama_model_var = tk.StringVar(value=self.config.get("ollama_model", ""))
        self.temperature_var = tk.DoubleVar(value=float(self.config.get("temperature", 0.7)))
        self.theme_var = tk.StringVar(value=self.config.get("theme", "Тёмная"))
        self.font_size_var = tk.StringVar(value=str(self.config.get("font_size", 11)))
        self.font_family_var = tk.StringVar(value=str(self.config.get("font_family", "Segoe UI")))

        identity = ttk.LabelFrame(content, text="Личность и поведение", padding=12)
        identity.pack(fill="x", pady=(0, 10))
        self._form_entry(identity, "Имя помощника", self.name_var)
        self._form_entry(identity, "Роль / специализация", self.role_var)
        self._form_entry(identity, "Характер", self.personality_var)
        self._form_entry(identity, "Стиль ответов", self.style_var)
        ttk.Label(identity, text="Мои дополнительные правила", style="Panel.TLabel").pack(anchor="w", pady=(9, 4))
        self.instructions_box = tk.Text(identity, height=5, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, padx=9, pady=8, font=(self.font_family, 10))
        self.instructions_box.pack(fill="x")
        # Text's class binding consumes wheel events before bind_all runs.
        # Route wheel events over this short field to the containing Settings page.
        self.instructions_box.bind(
            "<MouseWheel>", lambda event, target=canvas: self._scroll_canvas_from_mousewheel(event, target), add="+"
        )
        self.instructions_box.bind(
            "<Button-4>", lambda event, target=canvas: self._scroll_canvas_from_mousewheel(event, target), add="+"
        )
        self.instructions_box.bind(
            "<Button-5>", lambda event, target=canvas: self._scroll_canvas_from_mousewheel(event, target), add="+"
        )
        self.instructions_box.insert("1.0", self.config.get("instructions", ""))
        ttk.Label(identity, text="Температура ответов: ниже — строже и предсказуемее, выше — разнообразнее", style="MutedPanel.TLabel").pack(anchor="w", pady=(10, 4))
        temp_row = ttk.Frame(identity, style="Panel.TFrame")
        temp_row.pack(fill="x")
        ttk.Scale(temp_row, from_=0.0, to=1.5, variable=self.temperature_var, orient="horizontal").pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.temperature_value = ttk.Label(temp_row, text=f"{self.temperature_var.get():.1f}", style="Panel.TLabel", width=4)
        self.temperature_value.pack(side="right")
        self.temperature_var.trace_add("write", lambda *_: self.temperature_value.configure(text=f"{self.temperature_var.get():.1f}"))

        connection = ttk.LabelFrame(content, text="Подключение и режим работы", padding=12)
        connection.pack(fill="x", pady=(0, 10))
        ttk.Label(connection, text="Авто: сначала облачная модель при наличии ключа, затем локальная Ollama. В онлайн-режиме ваши запросы передаются выбранному API-провайдеру.", style="Panel.TLabel", wraplength=900, justify="left").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(connection, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Режим", style="Panel.TLabel").pack(side="left", padx=(0, 12))
        ttk.Combobox(row, textvariable=self.mode_var, state="readonly", values=["Авто", "Только онлайн", "Только локально"], width=22).pack(side="left")

        online = ttk.LabelFrame(content, text="Онлайн-модель · совместимый Chat Completions API", padding=12)
        online.pack(fill="x", pady=(0, 10))
        self._form_entry(online, "Адрес API", self.online_url_var)
        self._form_entry(online, "Название модели у провайдера", self.online_model_var)
        ttk.Label(online, text="API-ключ", style="Panel.TLabel").pack(anchor="w", pady=(8, 4))
        key_row = ttk.Frame(online, style="Panel.TFrame")
        key_row.pack(fill="x")
        self.api_key_entry = ttk.Entry(key_row, textvariable=self.api_key_var, show="●")
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        self.show_key_var = tk.BooleanVar(value=False)
        self._make_checkbox(key_row, "Показать", self.show_key_var, self._toggle_key, background_key="panel", wraplength=120).pack(side="left", padx=(8, 0))
        key_actions = ttk.Frame(online, style="Panel.TFrame")
        key_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(key_actions, text="Проверить онлайн-подключение", command=self.test_online).pack(side="left")
        ttk.Label(online, text="API-ключ нужен только для генерации ответов облачной моделью. Для интернет-поиска и чтения общедоступных страниц ключ не требуется. Ключ хранится в Windows DPAPI; подписка ChatGPT не включает API-запросы автоматически, их стоимость определяет провайдер.", style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(8, 0))

        local = ttk.LabelFrame(content, text="Локальная модель · Ollama", padding=12)
        local.pack(fill="x", pady=(0, 10))
        self._form_entry(local, "Адрес Ollama", self.ollama_url_var)
        self._form_entry(local, "Имя установленной модели", self.ollama_model_var)
        controls = ttk.Frame(local, style="Panel.TFrame")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Проверить Ollama", command=self.test_ollama).pack(side="left")
        ttk.Button(controls, text="Скопировать команду загрузки модели", command=self.copy_ollama_command).pack(side="left", padx=8)
        ttk.Label(local, text="Например: ollama pull qwen2.5:3b. Загрузка модели выполняется один раз; после этого локальный режим может работать без интернета.", style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(8, 0))

        drive = ttk.LabelFrame(content, text="Основное облако · Google Drive · сквозное шифрование", padding=12)
        drive.pack(fill="x", pady=(0, 10))
        ttk.Label(
            drive,
            text="Google Drive — основное хранилище ИИшки. Данные шифруются на компьютере до отправки и сохраняются в отдельной видимой папке «ISH Cloud». Приложение запрашивает только доступ drive.file к собственным файлам, а не ко всему диску. Укажи OAuth Desktop Client ID/Secret из Google Cloud Console и отдельную парольную фразу E2E.",
            style="MutedPanel.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self.google_drive_client_id_var = tk.StringVar(value=str(self.config.get("google_drive_client_id", "")))
        self.google_drive_client_secret_var = tk.StringVar()
        self.google_drive_e2e_password_var = tk.StringVar()
        self.google_drive_limit_var = tk.StringVar(value=str(self.config.get("google_drive_storage_limit_gb", 10)))
        self._form_entry(drive, "Google OAuth Client ID (тип Desktop app)", self.google_drive_client_id_var)
        ttk.Label(drive, text="Google OAuth Client Secret", style="Panel.TLabel").pack(anchor="w", pady=(8, 4))
        ttk.Entry(drive, textvariable=self.google_drive_client_secret_var, show="●").pack(fill="x")
        ttk.Label(drive, text="Пароль сквозного шифрования (не менее 10 символов; одинаковый на всех устройствах)", style="Panel.TLabel").pack(anchor="w", pady=(8, 4))
        ttk.Entry(drive, textvariable=self.google_drive_e2e_password_var, show="●").pack(fill="x")
        drive_options = ttk.Frame(drive, style="Panel.TFrame")
        drive_options.pack(fill="x", pady=(8, 2))
        ttk.Label(drive_options, text="Мягкий лимит папки ИИшки", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(drive_options, textvariable=self.google_drive_limit_var, state="readonly", width=8, values=["5", "8", "10"]).pack(side="left", padx=8)
        ttk.Label(drive_options, text="ГБ · это лимит приложения, не квота всего Google-аккаунта", style="MutedPanel.TLabel").pack(side="left")
        drive_actions = ttk.Frame(drive, style="Panel.TFrame")
        drive_actions.pack(fill="x", pady=(7, 2))
        ttk.Button(drive_actions, text="Подключить Google Drive", style="Accent.TButton", command=self.google_drive_connect).pack(side="left")
        ttk.Button(drive_actions, text="Отключить Google Drive", command=self.google_drive_disconnect).pack(side="left", padx=6)
        self.google_drive_status_var = tk.StringVar(value=("Google Drive подключён — основное облако." if self.google_drive_session_ready else "Google Drive не подключён. Сначала создай OAuth Desktop Client в Google Cloud Console."))
        ttk.Label(drive, textvariable=self.google_drive_status_var, style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(7, 0))

        cloud = ttk.LabelFrame(content, text="Резервное облако · Supabase · сквозное шифрование", padding=12)
        cloud.pack(fill="x", pady=(0, 10))
        ttk.Label(
            cloud,
            text="Supabase остаётся дополнительным хранилищем зашифрованного состояния приложения (диалоги, настройки и знания). ZIP-архивы резервных копий отправляются в Google Drive; если он недоступен, локальный архив сохраняется в очереди до восстановления связи. Supabase не заменяет очередь ZIP-копий. Настройка необязательна. Для Free учитывай 500 МБ размера базы данных (не 2 ГБ диска PostgreSQL).",
            style="MutedPanel.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self.cloud_url_var = tk.StringVar(value=str(self.config.get("cloud_url", "")))
        self.cloud_publishable_key_var = tk.StringVar(value=str(self.config.get("cloud_publishable_key", "")))
        self.cloud_email_var = tk.StringVar(value=str(self.config.get("cloud_email", "")))
        self.cloud_account_password_var = tk.StringVar()
        self.cloud_e2e_password_var = tk.StringVar()
        self.cloud_auto_sync_var = tk.BooleanVar(value=bool(self.config.get("cloud_auto_sync", True)))
        self._form_entry(cloud, "URL проекта Supabase", self.cloud_url_var)
        self._form_entry(cloud, "Публичный ключ Supabase (publishable key или legacy anon key)", self.cloud_publishable_key_var)
        self._form_entry(cloud, "Электронная почта аккаунта", self.cloud_email_var)
        ttk.Label(cloud, text="Пароль аккаунта Supabase", style="Panel.TLabel").pack(anchor="w", pady=(8, 4))
        ttk.Entry(cloud, textvariable=self.cloud_account_password_var, show="●").pack(fill="x")
        ttk.Label(cloud, text="Пароль E2E для резервной копии (может совпадать с Google Drive)", style="Panel.TLabel").pack(anchor="w", pady=(8, 4))
        ttk.Entry(cloud, textvariable=self.cloud_e2e_password_var, show="●").pack(fill="x")
        self._make_checkbox(cloud, "Автоматически синхронизировать данные с облаком", self.cloud_auto_sync_var, background_key="panel").pack(anchor="w", pady=(8, 4))
        cloud_actions = ttk.Frame(cloud, style="Panel.TFrame")
        cloud_actions.pack(fill="x", pady=(4, 2))
        ttk.Button(cloud_actions, text="Создать резервный аккаунт", command=self.cloud_sign_up).pack(side="left")
        ttk.Button(cloud_actions, text="Подключить резерв Supabase", style="Accent.TButton", command=self.cloud_sign_in).pack(side="left", padx=6)
        ttk.Button(cloud_actions, text="Синхронизировать сейчас", command=self.cloud_sync_now).pack(side="left", padx=6)
        ttk.Button(cloud_actions, text="Сохранить параметры", command=self.save_cloud_preferences).pack(side="left", padx=6)
        ttk.Button(cloud_actions, text="Отключить Supabase", command=self.cloud_sign_out).pack(side="left", padx=6)
        self.cloud_status_var = tk.StringVar(value=("Supabase подключён как резервное облако." if self.cloud_session_ready else "Резервный Supabase не подключён."))
        ttk.Label(cloud, textvariable=self.cloud_status_var, style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(7, 0))

        resources = ttk.LabelFrame(content, text="Управление нагрузкой компьютера", padding=12)
        resources.pack(fill="x", pady=(0, 10))
        ttk.Label(
            resources,
            text="Профиль учитывает твой ПК: Intel Core i7-12700K, 24 ГБ ОЗУ, GTX 1070 Ti и SSD. Фоновый поиск и облачная синхронизация запускаются с низким приоритетом. Профиль: до 5 ГБ ОЗУ для ИИ-процессов, резерв 8 ГБ свободной ОЗУ под Windows и другие программы, пауза фоновых задач при высокой загрузке CPU. При нагрузке других программ ИИшка замедляет или останавливает фоновые задачи; локальная модель получает меньше потоков и меньший контекст. 5 ГБ — мягкий верхний бюджет, а не обязательное потребление.",
            style="MutedPanel.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(0, 8))
        resource_row = ttk.Frame(resources, style="Panel.TFrame")
        resource_row.pack(fill="x")
        ttk.Label(resource_row, text="Максимальный бюджет ОЗУ для ИИ", style="Panel.TLabel").pack(side="left")
        self.background_ram_var = tk.StringVar(value=str(self.config.get("background_ram_limit_mb", 5120)))
        ttk.Combobox(resource_row, textvariable=self.background_ram_var, state="readonly", width=10, values=["1024", "2048", "3072", "4096", "5120"]).pack(side="left", padx=(8, 18))
        ttk.Label(resource_row, text="МБ", style="Panel.TLabel").pack(side="left")
        ttk.Label(resource_row, text="Порог нагрузки CPU", style="Panel.TLabel").pack(side="left", padx=(22, 6))
        self.background_cpu_var = tk.StringVar(value=str(self.config.get("background_cpu_limit_percent", 85)))
        ttk.Combobox(resource_row, textvariable=self.background_cpu_var, state="readonly", width=6, values=["70", "75", "80", "85", "90", "95"]).pack(side="left")
        ttk.Button(resources, text="Сохранить и применить профиль", command=self.save_resource_settings).pack(anchor="w", pady=(8, 0))
        self.resource_status_var = tk.StringVar(value="Фоновые задачи работают с низким приоритетом; мониторинг нагрузки включён.")
        ttk.Label(resources, textvariable=self.resource_status_var, style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(7, 0))

        appearance = ttk.LabelFrame(content, text="Внешний вид", padding=12)
        appearance.pack(fill="x", pady=(0, 10))
        appearance_row = ttk.Frame(appearance, style="Panel.TFrame")
        appearance_row.pack(fill="x")
        ttk.Label(appearance_row, text="Тема", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        ttk.Combobox(appearance_row, textvariable=self.theme_var, state="readonly", values=["Тёмная", "Светлая"], width=14).pack(side="left")
        ttk.Label(appearance_row, text="Шрифт", style="Panel.TLabel").pack(side="left", padx=(18, 8))
        ttk.Combobox(appearance_row, textvariable=self.font_family_var, state="readonly", values=["Segoe UI", "Arial", "Verdana"], width=14).pack(side="left")
        ttk.Label(appearance_row, text="Размер", style="Panel.TLabel").pack(side="left", padx=(18, 8))
        ttk.Combobox(appearance_row, textvariable=self.font_size_var, state="readonly", values=["10", "11", "12", "13", "14", "15", "16"], width=5).pack(side="left")

        backups = ttk.LabelFrame(content, text="Резервные копии памяти и данных", padding=12)
        backups.pack(fill="x", pady=(0, 10))
        ttk.Label(
            backups,
            text="Ежедневные копии содержат историю, память, настройки, базу знаний, навыки и плагины. Google Drive хранит отдельный AES-256-GCM зашифрованный архив; без E2E-пароля его нельзя прочитать. Локальная копия остаётся запасной, а при отсутствии интернета отправка в облако ставится в очередь. Папка расположена рядом с папкой установки, а не внутри неё — автообновление её не удалит.",
            style="MutedPanel.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(0, 8))
        self.backup_dir_var = tk.StringVar(value=str(self._backup_directory()))
        backup_location = ttk.Frame(backups, style="Panel.TFrame")
        backup_location.pack(fill="x", pady=(0, 7))
        ttk.Label(backup_location, text="Папка на диске:", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(backup_location, textvariable=self.backup_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(backup_location, text="Выбрать…", command=self.choose_backup_directory).pack(side="left", padx=(8, 0))

        backup_options = ttk.Frame(backups, style="Panel.TFrame")
        backup_options.pack(fill="x", pady=(0, 6))
        self.auto_backup_var = tk.BooleanVar(value=bool(self.config.get("auto_backup_enabled", True)))
        self._make_checkbox(
            backup_options, "Создавать резервную копию автоматически каждый день",
            self.auto_backup_var, background_key="panel",
        ).pack(side="left")
        ttk.Label(backup_options, text="Локально:", style="Panel.TLabel").pack(side="left", padx=(18, 5))
        self.backup_retention_var = tk.StringVar(value=str(self.config.get("backup_retention_count", 7)))
        ttk.Combobox(
            backup_options, textvariable=self.backup_retention_var, state="readonly",
            width=5, values=["3", "7", "14", "30"],
        ).pack(side="left")
        ttk.Label(backup_options, text="копий", style="MutedPanel.TLabel").pack(side="left", padx=(4, 0))

        cloud_backup_options = ttk.Frame(backups, style="Panel.TFrame")
        cloud_backup_options.pack(fill="x", pady=(2, 6))
        self.backup_cloud_enabled_var = tk.BooleanVar(value=bool(self.config.get("backup_cloud_enabled", True)))
        self._make_checkbox(
            cloud_backup_options, "Шифровать и отправлять копии в Google Drive",
            self.backup_cloud_enabled_var, background_key="panel",
        ).pack(side="left")
        ttk.Label(cloud_backup_options, text="В облаке хранить:", style="Panel.TLabel").pack(side="left", padx=(18, 5))
        self.backup_cloud_retention_var = tk.StringVar(value=str(self.config.get("backup_cloud_retention_count", 7)))
        ttk.Combobox(
            cloud_backup_options, textvariable=self.backup_cloud_retention_var, state="readonly",
            width=5, values=["3", "7", "14", "30"],
        ).pack(side="left")
        ttk.Label(cloud_backup_options, text="копий", style="MutedPanel.TLabel").pack(side="left", padx=(4, 0))

        supabase_backup_options = ttk.Frame(backups, style="Panel.TFrame")
        supabase_backup_options.pack(fill="x", pady=(2, 6))
        self.backup_supabase_enabled_var = tk.BooleanVar(value=bool(self.config.get("backup_supabase_enabled", False)))
        self._make_checkbox(
            supabase_backup_options,
            "Дополнительно дублировать зашифрованные ZIP-архивы в Supabase Storage",
            self.backup_supabase_enabled_var, background_key="panel",
        ).pack(side="left")
        ttk.Label(supabase_backup_options, text="В Supabase хранить:", style="Panel.TLabel").pack(side="left", padx=(18, 5))
        self.backup_supabase_retention_var = tk.StringVar(value=str(self.config.get("backup_supabase_retention_count", 7)))
        ttk.Combobox(
            supabase_backup_options, textvariable=self.backup_supabase_retention_var, state="readonly",
            width=5, values=["3", "7", "14", "30"],
        ).pack(side="left")
        ttk.Label(supabase_backup_options, text="копий", style="MutedPanel.TLabel").pack(side="left", padx=(4, 0))

        backup_actions = ttk.Frame(backups, style="Panel.TFrame")
        backup_actions.pack(fill="x", pady=(4, 4))
        ttk.Button(backup_actions, text="Создать копию сейчас", style="Accent.TButton", command=self.create_local_backup).pack(side="left")
        ttk.Button(backup_actions, text="Восстановить с диска…", command=self.restore_local_backup).pack(side="left", padx=7)
        ttk.Button(backup_actions, text="Восстановить из Google Drive…", command=self.restore_cloud_backup).pack(side="left", padx=7)
        ttk.Button(backup_actions, text="Отправить ожидающие копии", command=self.upload_pending_backups_now).pack(side="left")
        backup_actions2 = ttk.Frame(backups, style="Panel.TFrame")
        backup_actions2.pack(fill="x", pady=(2, 0))
        ttk.Button(backup_actions2, text="Открыть папку копий", command=self.open_backup_folder).pack(side="left")
        ttk.Button(backup_actions2, text="Восстановить из Supabase…", command=self.restore_supabase_backup).pack(side="left", padx=7)
        ttk.Button(backup_actions2, text="Сохранить настройки копирования", command=self.save_backup_settings).pack(side="left", padx=7)
        self.backup_status_var = tk.StringVar(value="Папка резервных копий: " + str(self._backup_directory()))
        ttk.Label(backups, textvariable=self.backup_status_var, style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(6, 0))

        bottom = ttk.Frame(content)
        bottom.pack(fill="x", pady=(4, 10))
        ttk.Button(bottom, text="Сохранить настройки", style="Accent.TButton", command=self.save_settings).pack(side="left")
        ttk.Button(bottom, text="Открыть папку данных", command=self.open_data_folder).pack(side="left", padx=8)
        ttk.Button(bottom, text="Сбросить настройки", command=self.reset_settings).pack(side="left")

    def _form_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor="w", pady=(7, 4))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.pack(fill="x")
        # Make clipboard paste reliable in packaged Windows builds as well as
        # through a right-click menu; keep the normal Entry copy/cut behavior.
        entry.bind("<Control-v>", self._paste_entry_shortcut, add="+")
        entry.bind("<Control-V>", self._paste_entry_shortcut, add="+")
        entry.bind("<Shift-Insert>", self._paste_entry_shortcut, add="+")
        menu = tk.Menu(entry, tearoff=0)
        menu.add_command(label="Вырезать", command=lambda field=entry: field.event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda field=entry: field.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda field=entry: self._paste_entry_clipboard(field))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda field=entry: field.selection_range(0, tk.END))
        entry.bind(
            "<Button-3>",
            lambda event, popup=menu: self._show_entry_clipboard_menu(event, popup),
            add="+",
        )
        entry._moya_clipboard_menu = menu

    @staticmethod
    def _paste_entry_clipboard(entry: ttk.Entry) -> None:
        try:
            clipboard_text = entry.clipboard_get()
        except tk.TclError:
            return
        try:
            if entry.selection_present():
                start, end = entry.index("sel.first"), entry.index("sel.last")
            else:
                start = end = entry.index("insert")
            entry.delete(start, end)
            entry.insert(start, clipboard_text)
            entry.icursor(start + len(clipboard_text))
        except tk.TclError:
            return

    def _paste_entry_shortcut(self, event: tk.Event) -> str:
        self._paste_entry_clipboard(event.widget)
        return "break"

    @staticmethod
    def _show_entry_clipboard_menu(event: tk.Event, menu: tk.Menu) -> str:
        event.widget.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _build_memory_page(self) -> None:
        page = self.pages["memory"]
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text="Память ИИ", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(page, text="Память хранится локально и попадает в зашифрованную облачную копию при включённой синхронизации.", style="Muted.TLabel", wraplength=900).grid(row=1, column=0, sticky="w", pady=(6, 12))
        body = ttk.Frame(page)
        body.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.memory_list = tk.Listbox(body, relief="flat", borderwidth=0, highlightthickness=0, selectbackground="#66508F", font=(self.font_family, 11), activestyle="none")
        self.memory_list.grid(row=0, column=0, sticky="nsew")
        memory_scroll = ttk.Scrollbar(body, orient="vertical", command=self.memory_list.yview)
        memory_scroll.grid(row=0, column=1, sticky="ns")
        self.memory_list.configure(yscrollcommand=memory_scroll.set)
        bottom = ttk.Frame(page, padding=(0, 12, 0, 0))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.memory_entry_var = tk.StringVar()
        entry = ttk.Entry(bottom, textvariable=self.memory_entry_var)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", lambda _e: self.add_memory())
        ttk.Button(bottom, text="Добавить", style="Accent.TButton", command=self.add_memory).grid(row=0, column=1, padx=3)
        ttk.Button(bottom, text="Изменить", command=self.edit_memory).grid(row=0, column=2, padx=3)
        ttk.Button(bottom, text="Удалить", command=self.remove_memory).grid(row=0, column=3, padx=3)
        ttk.Button(bottom, text="Очистить всё", command=self.clear_memory).grid(row=0, column=4, padx=(3, 0))
        self.memory_count_var = tk.StringVar(value="0 записей")
        ttk.Label(page, textvariable=self.memory_count_var, style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.auto_memory_var = tk.BooleanVar(value=bool(self.config.get("auto_memory", True)))
        self._make_checkbox(page, "Автоматически запоминать явные факты и предпочтения из моих сообщений", self.auto_memory_var, self._toggle_auto_memory, background_key="bg", wraplength=820).grid(row=5, column=0, sticky="w", pady=(12, 0))
        ttk.Label(page, text="Запоминаются явные факты. Пароли, ключи, контакты и чувствительные сведения отфильтровываются.", style="Muted.TLabel", wraplength=900).grid(row=6, column=0, sticky="w", pady=(5, 0))
        self.memory_semantic_var = tk.BooleanVar(value=bool(self.config.get("memory_semantic_enabled", True)))
        self._make_checkbox(page, "Искать воспоминания по смыслу через локальную Ollama", self.memory_semantic_var, self._toggle_memory_semantic, background_key="bg", wraplength=820).grid(row=7, column=0, sticky="w", pady=(10, 0))
        embedding_row = ttk.Frame(page)
        embedding_row.grid(row=8, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(embedding_row, text="Модель смыслового поиска:").pack(side="left")
        self.memory_embedding_model_var = tk.StringVar(value=str(self.config.get("memory_embedding_model", "nomic-embed-text")))
        ttk.Entry(embedding_row, textvariable=self.memory_embedding_model_var, width=28).pack(side="left", padx=(8, 6))
        ttk.Button(embedding_row, text="Сохранить", command=self.save_memory_semantic_settings).pack(side="left")
        ttk.Label(page, text="Для векторного поиска установи модель в Ollama: ollama pull nomic-embed-text. Если модель или Ollama недоступна, ИИ автоматически использует локальный поиск по словам и похожим понятиям. Векторный кеш остаётся на компьютере.", style="Muted.TLabel", wraplength=900).grid(row=9, column=0, sticky="w", pady=(5, 0))
        self._refresh_memory_list()

    def _build_windows_page(self) -> None:
        page = self.pages["windows"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        ttk.Label(page, text="Управление Windows и голос", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(page, text="Ишка может открыть выбранные приложения и стандартные папки. Произвольные команды PowerShell/CMD не выполняются.", style="Muted.TLabel", wraplength=900).grid(row=1, column=0, sticky="w", pady=(0, 12))

        # This page contains more controls than fit in a typical laptop window.
        # Put the whole Windows/voice content in a Canvas so the global wheel
        # handler can find the nearest Canvas ancestor for every child widget.
        scroll_canvas = tk.Canvas(page, highlightthickness=0, borderwidth=0, takefocus=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scroll_canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        body = ttk.Frame(scroll_canvas)
        body_window = scroll_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda _event: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")),
        )
        scroll_canvas.bind(
            "<Configure>",
            lambda event: scroll_canvas.itemconfigure(body_window, width=event.width),
        )
        self.windows_page_canvas = scroll_canvas
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        apps = ttk.LabelFrame(body, text="Запуск приложений", padding=12)
        apps.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 10))
        app_items = [("Блокнот", "блокнот"), ("Калькулятор", "калькулятор"), ("Проводник", "проводник"), ("Paint", "paint"), ("Диспетчер задач", "диспетчер задач"), ("Панель управления", "панель управления"), ("Параметры Windows", "настройки")]
        for index, (label, key) in enumerate(app_items):
            ttk.Button(apps, text=label, command=lambda item=key: self._run_windows_app(item)).grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)
        apps.columnconfigure(0, weight=1)
        apps.columnconfigure(1, weight=1)

        folders = ttk.LabelFrame(body, text="Открыть стандартную папку", padding=12)
        folders.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 10))
        folder_items = [("Рабочий стол", "рабочий стол"), ("Загрузки", "загрузки"), ("Документы", "документы"), ("Изображения", "изображения"), ("Музыка", "музыка"), ("Видео", "видео"), ("Домашняя папка", "домой")]
        for index, (label, key) in enumerate(folder_items):
            ttk.Button(folders, text=label, command=lambda item=key: self._run_windows_folder(item)).grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)
        folders.columnconfigure(0, weight=1)
        folders.columnconfigure(1, weight=1)

        voice = ttk.LabelFrame(body, text="Голосовой помощник", padding=12)
        voice.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        voice.columnconfigure(0, weight=1)
        self.voice_status_var = tk.StringVar(value="Микрофон отключён. Разреши доступ в этом окне, когда захочешь говорить с ИИ.")
        ttk.Label(voice, text="Голосовой ввод и озвучивание управляются прямо здесь. Приложение не слушает постоянно: запись начинается только после нажатия кнопки.", style="Panel.TLabel", wraplength=740).grid(row=0, column=0, sticky="w")
        self.microphone_enabled_var = tk.BooleanVar(value=bool(self.config.get("microphone_enabled", False)))
        self._make_checkbox(voice, "Разрешить приложению использовать микрофон", self.microphone_enabled_var, self._toggle_microphone_access, background_key="panel").grid(row=1, column=0, sticky="w", pady=(8, 4))
        actions = ttk.Frame(voice, style="Panel.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(4, 4))
        main_actions = ttk.Frame(actions, style="Panel.TFrame")
        main_actions.pack(fill="x", pady=(0, 6))
        self.voice_start_button = ttk.Button(main_actions, text="🎙 Начать говорить", style="Accent.TButton", command=self.start_voice_input, state="normal" if self.microphone_enabled_var.get() else "disabled")
        self.voice_start_button.pack(side="left", padx=(0, 6))
        self.voice_stop_button = ttk.Button(main_actions, text="■ Остановить микрофон", command=self.stop_voice_input, state="disabled")
        self.voice_stop_button.pack(side="left", padx=6)
        ttk.Button(main_actions, text="🔊 Озвучить ответ", command=self.speak_last_answer).pack(side="left", padx=6)
        ttk.Button(main_actions, text="Персонаж", command=self.toggle_avatar).pack(side="left", padx=6)
        secondary_actions = ttk.Frame(actions, style="Panel.TFrame")
        secondary_actions.pack(fill="x")
        self.voice_tts_var = tk.BooleanVar(value=bool(self.config.get("voice_tts", False)))
        self._make_checkbox(secondary_actions, "Автоматически озвучивать ответы", self.voice_tts_var, self._toggle_voice_tts, background_key="panel", wraplength=280).pack(side="left", padx=(0, 12))
        ttk.Button(secondary_actions, text="Настройки микрофона Windows", command=self.open_windows_microphone_privacy).pack(side="left")

        voice_library = ttk.LabelFrame(voice, text="Голоса озвучивания ответов", padding=10)
        voice_library.grid(row=3, column=0, sticky="ew", pady=(10, 4))
        voice_library.columnconfigure(1, weight=1)
        ttk.Label(voice_library, text="Выбери голос. Скачанный голос хранится на этом компьютере и работает без отправки текста в интернет.", style="MutedPanel.TLabel", wraplength=720).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(voice_library, text="Русский голос Piper", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.tts_voice_var = tk.StringVar(value="")
        self.tts_voice_combo = ttk.Combobox(voice_library, textvariable=self.tts_voice_var, state="readonly", width=42)
        self.tts_voice_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.tts_voice_combo.bind("<<ComboboxSelected>>", self._on_tts_voice_selected)
        ttk.Button(voice_library, text="Загрузить голос", style="Accent.TButton", command=self.download_selected_tts_voice).grid(row=1, column=2, sticky="ew", padx=(0, 6))
        ttk.Button(voice_library, text="Удалить голос", command=self.delete_selected_tts_voice).grid(row=1, column=3, sticky="ew")
        voice_actions = ttk.Frame(voice_library, style="Panel.TFrame")
        voice_actions.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(voice_actions, text="Использовать системный голос Windows", command=self.use_system_tts_voice).pack(side="left")
        ttk.Button(voice_actions, text="Прослушать пример", command=self.preview_selected_tts_voice).pack(side="left", padx=(8, 0))
        self.tts_voice_progress = ttk.Progressbar(voice_library, orient="horizontal", mode="determinate", maximum=100)
        self.tts_voice_progress.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 4))
        self.tts_voice_status_var = tk.StringVar(value="Системный голос Windows. Можно скачать локальный русский голос Piper (около 60 МБ).")
        ttk.Label(voice_library, textvariable=self.tts_voice_status_var, style="MutedPanel.TLabel", wraplength=740).grid(row=4, column=0, columnspan=4, sticky="w")
        self._refresh_tts_voice_controls()

        ttk.Label(voice, textvariable=self.voice_status_var, style="MutedPanel.TLabel", wraplength=740).grid(row=4, column=0, sticky="w", pady=(7, 0))
        ttk.Label(page, text="Распознавание речи отправляет аудиофрагмент в сервис Google Speech Recognition через интернет. Голоса Piper скачиваются один раз и озвучивают ответы локально. Системный голос Windows не требует загрузки. Микрофон остаётся выключенным, пока ты явно не разрешишь доступ.", style="Muted.TLabel", wraplength=740).grid(row=3, column=0, sticky="w", pady=(4, 0))

    def _build_workshop_page(self) -> None:
        page = self.pages["workshop"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        ttk.Label(page, text="Навыки, плагины и развитие", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        canvas = tk.Canvas(page, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.workshop_page_canvas = canvas
        content = ttk.Frame(canvas, padding=(2, 2, 12, 18))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        skills = ttk.LabelFrame(content, text="Мои навыки", padding=12)
        skills.pack(fill="x", pady=(0, 10))
        ttk.Label(skills, text="Навык — это сохранённая инструкция, которую ИИ будет учитывать в будущих ответах.", style="MutedPanel.TLabel", wraplength=880).pack(anchor="w")
        self.skill_list = tk.Listbox(skills, height=6, relief="flat", borderwidth=0, highlightthickness=0, activestyle="none", font=(self.font_family, 10))
        self.skill_list.pack(fill="x", pady=(8, 8))
        skill_actions = ttk.Frame(skills, style="Panel.TFrame")
        skill_actions.pack(fill="x")
        ttk.Button(skill_actions, text="＋ Создать навык", style="Accent.TButton", command=self.create_skill).pack(side="left")
        ttk.Button(skill_actions, text="Включить / выключить", command=self.toggle_selected_skill).pack(side="left", padx=8)
        ttk.Button(skill_actions, text="Удалить", command=self.delete_selected_skill).pack(side="left")
        ttk.Button(skill_actions, text="Открыть папку навыков", command=lambda: self._open_local_folder(self.plugin_manager.skills_dir)).pack(side="right")

        plugins = ttk.LabelFrame(content, text="Python-плагины", padding=12)
        plugins.pack(fill="x", pady=(0, 10))
        ttk.Label(plugins, text="Плагины могут добавлять новые команды. Включай только код, который сам написал или внимательно проверил: Python-плагин не изолирован и получает права твоей учётной записи Windows.", style="MutedPanel.TLabel", wraplength=880).pack(anchor="w")
        self.python_plugins_var = tk.BooleanVar(value=bool(self.config.get("plugins_enabled", False)))
        self._make_checkbox(plugins, "Разрешить выполнение моих Python-плагинов", self.python_plugins_var, self._toggle_python_plugins, background_key="panel").pack(anchor="w", pady=(8, 4))
        plugin_actions = ttk.Frame(plugins, style="Panel.TFrame")
        plugin_actions.pack(fill="x")
        ttk.Button(plugin_actions, text="Создать шаблон плагина", command=self.create_python_plugin).pack(side="left")
        ttk.Button(plugin_actions, text="Открыть папку плагинов", command=lambda: self._open_local_folder(self.plugin_manager.plugins_dir)).pack(side="left", padx=8)
        self.plugin_list_var = tk.StringVar(value="")
        ttk.Label(plugins, textvariable=self.plugin_list_var, style="MutedPanel.TLabel", wraplength=880).pack(anchor="w", pady=(8, 0))

        self_dev = ttk.LabelFrame(content, text="Саморазвитие и изменение собственного кода", padding=12)
        self_dev.pack(fill="x", pady=(0, 10))
        ttk.Label(self_dev, text="Опиши улучшение. Модель подготовит единый diff для выбранного Python-модуля и соответствующего tests/test_*.py. Пакет сохраняется вместе с тестами и проверяется в Windows Sandbox; изменения не применяются автоматически.", style="MutedPanel.TLabel", wraplength=880).pack(anchor="w")
        self.improve_target_var = tk.StringVar(value="main.py")
        target_row = ttk.Frame(self_dev, style="Panel.TFrame")
        target_row.pack(fill="x", pady=(8, 4))
        ttk.Label(target_row, text="Файл проекта", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        ttk.Combobox(target_row, textvariable=self.improve_target_var, state="readonly", values=editable_project_files(), width=38).pack(side="left")
        self.improve_dependency_var = tk.StringVar(value="Связи модулей: будут проверены перед анализом.")
        ttk.Label(self_dev, textvariable=self.improve_dependency_var, style="MutedPanel.TLabel", wraplength=880).pack(anchor="w", pady=(2, 6))
        prompt_frame = ttk.Frame(self_dev, style="Panel.TFrame")
        prompt_frame.pack(fill="x", pady=(4, 2))
        self.improve_prompt_box = tk.Text(prompt_frame, height=4, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, padx=9, pady=8, font=(self.font_family, 9))
        prompt_scroll = ttk.Scrollbar(prompt_frame, orient="vertical", command=self.improve_prompt_box.yview)
        self.improve_prompt_box.configure(yscrollcommand=prompt_scroll.set)
        self.improve_prompt_box.pack(side="left", fill="both", expand=True)
        prompt_scroll.pack(side="right", fill="y")
        self.improve_prompt_box.insert("1.0", "Например: добавь кнопку, которая экспортирует память в JSON.")
        self._install_text_clipboard_menu(self.improve_prompt_box)
        self._bind_nested_text_scrolling(self.improve_prompt_box, canvas)
        self._bind_nested_text_scrolling(prompt_scroll, canvas, text_widget=self.improve_prompt_box)
        prompt_actions = ttk.Frame(self_dev, style="Panel.TFrame")
        prompt_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(prompt_actions, text="Копировать задание", command=self.copy_improvement_task).pack(side="left")
        ttk.Button(prompt_actions, text="Вставить из буфера", command=self.paste_improvement_task).pack(side="left", padx=8)
        developer_models = ttk.LabelFrame(self_dev, text="Модели по ролям (необязательно)", padding=8)
        developer_models.pack(fill="x", pady=(0, 8))
        ttk.Label(developer_models, text="Оставь поле пустым, чтобы использовать основную модель. Указывай имя модели для текущего режима (Ollama или онлайн).", style="MutedPanel.TLabel", wraplength=860).pack(anchor="w")
        self.developer_model_vars = {}
        role_row = ttk.Frame(developer_models, style="Panel.TFrame")
        role_row.pack(fill="x", pady=(6, 0))
        for role_key, role_label in (
            ("architect", "Архитектор"),
            ("coder", "Программист"),
            ("reviewer", "Ревизор"),
        ):
            ttk.Label(role_row, text=role_label, style="Panel.TLabel").pack(side="left", padx=(0, 4))
            variable = tk.StringVar(value=str(self.config.get(f"developer_{role_key}_model", "")))
            self.developer_model_vars[role_key] = variable
            ttk.Entry(role_row, textvariable=variable, width=17).pack(side="left", padx=(0, 10))
        ttk.Button(role_row, text="Сохранить модели", command=self.save_developer_models).pack(side="left")
        self.improve_auto_var = tk.BooleanVar(value=bool(self.config.get("self_improve_auto_enabled", False)))
        self._make_checkbox(self_dev, "Автоанализ выбранного файла раз в сутки (без автоматического изменения кода)", self.improve_auto_var, self._toggle_auto_improvement, background_key="panel").pack(anchor="w", pady=(0, 6))
        analysis_actions = ttk.Frame(self_dev, style="Panel.TFrame")
        analysis_actions.pack(fill="x", pady=(0, 6))
        ttk.Button(analysis_actions, text="Автоанализ выбранного файла", command=self.analyze_improvements).pack(side="left")
        ttk.Button(analysis_actions, text="Копировать текст улучшения", command=self.copy_selected_improvement).pack(side="left", padx=8)
        ttk.Button(analysis_actions, text="Подготовить diff выбранного предложения", style="Accent.TButton", command=self.prepare_selected_improvement).pack(side="left", padx=8)
        self.background_developer_button = ttk.Button(analysis_actions, text="Фоновый разработчик: создать и проверить", command=self.run_background_developer)
        self.background_developer_button.pack(side="left", padx=8)
        improvement_panel = ttk.Frame(self_dev, style="Panel.TFrame")
        improvement_panel.pack(fill="both", expand=True, pady=(0, 6))
        improvement_panel.columnconfigure(0, weight=1)
        improvement_panel.columnconfigure(1, weight=2)
        improvement_panel.rowconfigure(1, weight=1)
        ttk.Label(improvement_panel, text="Предложения", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(improvement_panel, text="Как сейчас → как будет", style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        self.improvement_listbox = tk.Listbox(improvement_panel, height=4, exportselection=False, activestyle="dotbox", bg=self.colors["input"], fg=self.colors["text"], selectbackground=self.colors["select"], selectforeground=self.colors["text"], relief="flat", highlightthickness=0, font=(self.font_family, 9))
        self.improvement_listbox.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.improvement_listbox.bind("<<ListboxSelect>>", self._show_selected_improvement)
        preview_frame = ttk.Frame(improvement_panel, style="Panel.TFrame")
        preview_frame.grid(row=1, column=1, sticky="nsew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.improvement_preview = tk.Text(preview_frame, height=7, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, padx=9, pady=8, font=(self.font_family, 9), bg=self.colors["input"], fg=self.colors["text"])
        preview_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.improvement_preview.yview)
        self.improvement_preview.configure(yscrollcommand=preview_scroll.set)
        self.improvement_preview.grid(row=0, column=0, sticky="nsew")
        preview_scroll.grid(row=0, column=1, sticky="ns")
        self.improvement_preview.insert("1.0", "Включи автоанализ или запусти его вручную.")
        self.improvement_preview.configure(state="disabled")
        self._install_text_clipboard_menu(self.improvement_preview, readonly=True)
        self._bind_nested_text_scrolling(self.improvement_preview, canvas)
        self._bind_nested_text_scrolling(preview_scroll, canvas, text_widget=self.improvement_preview)
        ttk.Button(self_dev, text="Подготовить diff по моему описанию", style="Accent.TButton", command=self.generate_improvement_patch).pack(anchor="w")
        patch_frame = ttk.Frame(self_dev, style="Panel.TFrame")
        patch_frame.pack(fill="both", expand=True, pady=(8, 6))
        patch_frame.rowconfigure(0, weight=1)
        patch_frame.columnconfigure(0, weight=1)
        self.patch_preview = tk.Text(patch_frame, height=12, wrap="none", relief="flat", borderwidth=0, highlightthickness=0, padx=9, pady=8, font=("Consolas", 9))
        patch_y = ttk.Scrollbar(patch_frame, orient="vertical", command=self.patch_preview.yview)
        patch_x = ttk.Scrollbar(patch_frame, orient="horizontal", command=self.patch_preview.xview)
        self.patch_preview.configure(yscrollcommand=patch_y.set, xscrollcommand=patch_x.set)
        self.patch_preview.grid(row=0, column=0, sticky="nsew")
        patch_y.grid(row=0, column=1, sticky="ns")
        patch_x.grid(row=1, column=0, sticky="ew")
        self._bind_nested_text_scrolling(self.patch_preview, canvas)
        self._bind_nested_text_scrolling(patch_y, canvas, text_widget=self.patch_preview)
        patch_actions = ttk.Frame(self_dev, style="Panel.TFrame")
        patch_actions.pack(fill="x")
        ttk.Button(patch_actions, text="Сохранить diff", command=self.save_patch_file).pack(side="left")
        ttk.Button(patch_actions, text="Применить проверенный diff", style="Accent.TButton", command=self.apply_improvement).pack(side="left", padx=8)
        ttk.Button(patch_actions, text="Открыть папку исходников", command=lambda: self._open_local_folder(project_dir())).pack(side="left", padx=8)

        sandbox_frame = ttk.LabelFrame(self_dev, text="Защищённое тестирование — Windows Sandbox", padding=10)
        sandbox_frame.pack(fill="x", pady=(8, 6))
        ttk.Label(
            sandbox_frame,
            text="Перед запуском кода, созданного ИИ, ISH проверяет Windows Sandbox. При необходимости приложение установит системный компонент через запрос администратора Windows. Может потребоваться перезагрузка; сама программа компьютер не перезагружает. Без готовой песочницы тестовый код не запускается.",
            style="MutedPanel.TLabel", wraplength=880, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self.windows_sandbox_status_var = tk.StringVar(value="Состояние Windows Sandbox ещё не проверено.")
        ttk.Label(sandbox_frame, textvariable=self.windows_sandbox_status_var, style="MutedPanel.TLabel", wraplength=880).pack(anchor="w", pady=(0, 8))
        sandbox_actions = ttk.Frame(sandbox_frame, style="Panel.TFrame")
        sandbox_actions.pack(fill="x")
        self.sandbox_install_button = ttk.Button(sandbox_actions, text="Установить Windows Sandbox", command=self.install_windows_sandbox)
        self.sandbox_install_button.pack(side="left")
        ttk.Button(sandbox_actions, text="Проверить состояние", command=self.refresh_windows_sandbox_status).pack(side="left", padx=8)

        delivery_actions = ttk.Frame(self_dev, style="Panel.TFrame")
        delivery_actions.pack(fill="x", pady=(6, 2))
        ttk.Button(delivery_actions, text="Сохранить изменённые файлы в Updates", command=self.save_improvement_bundle).pack(side="left")
        ttk.Button(delivery_actions, text="Тестировать последнее предложение", command=self.test_latest_improvement_bundle).pack(side="left", padx=8)
        ttk.Button(delivery_actions, text="Создать Draft PR на GitHub", style="Accent.TButton", command=self.create_improvement_pr).pack(side="left", padx=8)
        ttk.Button(delivery_actions, text="Открыть Updates", command=self.open_updates_folder).pack(side="left", padx=8)

        github_frame = ttk.LabelFrame(self_dev, text="GitHub Draft PR — настройки", padding=8)
        github_frame.pack(fill="x", pady=(6, 6))
        github_row = ttk.Frame(github_frame, style="Panel.TFrame")
        github_row.pack(fill="x", pady=2)
        ttk.Label(github_row, text="Репозиторий", style="Panel.TLabel").pack(side="left", padx=(0, 6))
        self.github_pr_repo_var = tk.StringVar(value=str(self.config.get("github_pr_repo", "MrNike227/MoyaIshka")))
        ttk.Entry(github_row, textvariable=self.github_pr_repo_var, width=30).pack(side="left")
        ttk.Label(github_row, text="Базовая ветка", style="Panel.TLabel").pack(side="left", padx=(12, 6))
        self.github_pr_base_var = tk.StringVar(value=str(self.config.get("github_pr_base", "main")))
        ttk.Entry(github_row, textvariable=self.github_pr_base_var, width=14).pack(side="left")
        token_row = ttk.Frame(github_frame, style="Panel.TFrame")
        token_row.pack(fill="x", pady=2)
        ttk.Label(token_row, text="GitHub token", style="Panel.TLabel").pack(side="left", padx=(0, 6))
        self.github_pr_token_var = tk.StringVar(value=unprotect_github_pr_token(self.config))
        ttk.Entry(token_row, textvariable=self.github_pr_token_var, show="*", width=52).pack(side="left", fill="x", expand=True)
        ttk.Button(token_row, text="Сохранить настройки GitHub", command=self.save_github_pr_settings).pack(side="left", padx=(8, 0))
        ttk.Label(
            github_frame,
            text="Нужен Fine-grained Personal Access Token: Contents — Read and write, Pull requests — Read and write, Metadata — Read-only. Токен защищается DPAPI. Создаётся отдельная ветка и Draft PR; main не изменяется, релиз не создаётся.",
            style="MutedPanel.TLabel", wraplength=860,
        ).pack(anchor="w", pady=(4, 0))
        self.improve_status_var = tk.StringVar(value="Изменение кода требует подключения онлайн- или локальной модели.")
        ttk.Label(self_dev, textvariable=self.improve_status_var, style="MutedPanel.TLabel", wraplength=880).pack(anchor="w", pady=(8, 0))

        updates = ttk.LabelFrame(content, text="Автоматические обновления", padding=12)
        updates.pack(fill="x", pady=(0, 10))
        ttk.Label(updates, text="Выбери корневую папку контейнера. Внутри будут две независимые папки: App — установленная программа, Updates — предложения самоанализа и подготовленные изменения. Обновлятор заменяет только App и не затрагивает Updates.", style="MutedPanel.TLabel", wraplength=880).pack(anchor="w")
        self.update_repo_var = tk.StringVar(value=str(self.config.get("update_repo", "")))
        repo_row = ttk.Frame(updates, style="Panel.TFrame")
        repo_row.pack(fill="x", pady=(8, 4))
        ttk.Label(repo_row, text="GitHub-репозиторий", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(repo_row, textvariable=self.update_repo_var, width=38).pack(side="left")
        install_row = ttk.Frame(updates, style="Panel.TFrame")
        install_row.pack(fill="x", pady=(8, 2))
        ttk.Label(install_row, text="Корневая папка контейнера", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        initial_install_dir = str(self.config.get("install_root_dir", "")).strip()
        if not initial_install_dir:
            initial_install_dir = str(default_install_root(legacy_install_dir=self.config.get("install_dir"), running_exe=Path(sys.executable) if getattr(sys, "frozen", False) else None))
        self.update_install_dir_var = tk.StringVar(value=initial_install_dir)
        ttk.Entry(install_row, textvariable=self.update_install_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(install_row, text="Выбрать папку…", command=self.browse_install_dir).pack(side="left", padx=(8, 0))
        ttk.Button(install_row, text="Открыть App", command=self.open_install_folder).pack(side="left", padx=(6, 0))
        current_run_path = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve()
        current_run_label = str(current_run_path if getattr(sys, "frozen", False) else current_run_path.parent)
        target_exe_label = str(Path(initial_install_dir).expanduser().resolve() / "App" / "ISH.exe")
        updates_path_label = str(Path(initial_install_dir).expanduser().resolve() / "Updates")
        temp_path_label = str(Path(initial_install_dir).expanduser().resolve() / "Temp")
        self.actual_run_path_var = tk.StringVar(
            value=f"Фактически запущена: {current_run_label}\nНовая папка App: {target_exe_label}\nПредложения: {updates_path_label}\nВременные файлы: {temp_path_label}"
        )
        ttk.Label(updates, textvariable=self.actual_run_path_var, style="MutedPanel.TLabel", wraplength=880).pack(anchor="w", pady=(4, 2))
        self.auto_update_var = tk.BooleanVar(value=bool(self.config.get("auto_update_check", True)))
        self._make_checkbox(updates, "Проверять наличие обновлений при запуске", self.auto_update_var, background_key="panel").pack(anchor="w", pady=4)
        self.auto_cleanup_old_versions_var = tk.BooleanVar(
            value=bool(self.config.get("auto_cleanup_old_versions", True))
        )
        self._make_checkbox(
            updates,
            "После успешного обновления автоматически искать и удалять старые копии ISH и MoyaIshka",
            self.auto_cleanup_old_versions_var,
            background_key="panel",
        ).pack(anchor="w", pady=4)
        update_buttons = ttk.Frame(updates, style="Panel.TFrame")
        update_buttons.pack(fill="x")
        ttk.Button(update_buttons, text="Проверить обновления", command=self.check_for_updates).pack(side="left")
        ttk.Button(update_buttons, text="Сохранить настройки обновлений", command=self.save_update_settings).pack(side="left", padx=8)
        ttk.Button(update_buttons, text="Перенести программу в App", command=self.install_current_build_to_selected_folder).pack(side="left", padx=8)
        ttk.Button(update_buttons, text="Открыть Updates", command=self.open_updates_folder).pack(side="left", padx=8)
        ttk.Button(update_buttons, text="Поиск устаревших версий", command=self.search_old_versions).pack(side="left", padx=8)
        ttk.Button(update_buttons, text="Открыть журнал обновлений", command=self.open_update_log).pack(side="left", padx=8)
        self.update_status_var = tk.StringVar(value="Репозиторий не задан. Выбери папку установки и сохрани настройки.")
        ttk.Label(updates, textvariable=self.update_status_var, style="MutedPanel.TLabel", wraplength=880).pack(anchor="w", pady=(8, 0))
        self._refresh_skill_list()

    def _build_research_page(self) -> None:
        page = self.pages["research"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        ttk.Label(page, text="Интернет, исследования и база знаний", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        canvas = tk.Canvas(page, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        content = ttk.Frame(canvas, padding=(2, 2, 12, 18))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        intro = ttk.LabelFrame(content, text="Доступ в интернет", padding=12)
        intro.pack(fill="x", pady=(0, 10))
        ttk.Label(
            intro,
            text="Интернет-поиск не требует API-ключа: ИИшка ищет общедоступные страницы, читает ограниченное число источников и сохраняет результаты в библиотеку знаний. При подключённом облаке с включённой синхронизацией зашифрованная копия автоматически отправляется в Supabase. Фоновое исследование приостанавливается, если компьютер занят, загрузка CPU высока или свободной ОЗУ осталось менее 8 ГБ.",
            style="Panel.TLabel", wraplength=900, justify="left"
        ).pack(anchor="w")
        self.web_enabled_var = tk.BooleanVar(value=bool(self.config.get("web_search_enabled", True)))
        self._make_checkbox(intro, "Разрешить поиск и чтение публичных страниц", self.web_enabled_var, background_key="panel").pack(anchor="w", pady=(8, 2))
        self.auto_search_current_var = tk.BooleanVar(value=bool(self.config.get("auto_search_current", False)))
        self._make_checkbox(intro, "Автоматически искать свежие данные, когда вопрос явно зависит от текущей информации", self.auto_search_current_var, background_key="panel").pack(anchor="w", pady=2)
        self.use_research_library_var = tk.BooleanVar(value=bool(self.config.get("use_research_library", True)))
        self._make_checkbox(intro, "Использовать сохранённые источники в ответах ИИ", self.use_research_library_var, background_key="panel").pack(anchor="w", pady=2)

        search = ttk.LabelFrame(content, text="Поиск по запросу", padding=12)
        search.pack(fill="x", pady=(0, 10))
        ttk.Label(search, text="Напиши тему или вопрос. В чате также можно начать сообщение с «поищи в интернете …».", style="MutedPanel.TLabel", wraplength=900).pack(anchor="w")
        self.research_query_var = tk.StringVar()
        ttk.Entry(search, textvariable=self.research_query_var).pack(fill="x", pady=(7, 8))
        options = ttk.Frame(search, style="Panel.TFrame")
        options.pack(fill="x")
        ttk.Label(options, text="Результатов", style="Panel.TLabel").pack(side="left")
        self.research_results_var = tk.StringVar(value=str(self.config.get("research_results_limit", 10)))
        ttk.Combobox(options, textvariable=self.research_results_var, state="readonly", width=5, values=["3", "5", "8", "10"]).pack(side="left", padx=(6, 16))
        ttk.Label(options, text="Читать страниц", style="Panel.TLabel").pack(side="left")
        self.research_fetch_var = tk.StringVar(value=str(self.config.get("research_fetch_pages", 5)))
        ttk.Combobox(options, textvariable=self.research_fetch_var, state="readonly", width=5, values=["0", "1", "2", "3", "5"]).pack(side="left", padx=(6, 16))
        ttk.Button(options, text="Искать и сохранить", style="Accent.TButton", command=self.start_manual_research).pack(side="left")
        self.research_status_var = tk.StringVar(value="Поиск готов. Фоновое исследование выполняется по расписанию, пока компьютер не занят.")
        ttk.Label(search, textvariable=self.research_status_var, style="MutedPanel.TLabel", wraplength=900).pack(anchor="w", pady=(8, 0))

        auto = ttk.LabelFrame(content, text="Самостоятельное исследование по темам", padding=12)
        auto.pack(fill="x", pady=(0, 10))
        ttk.Label(auto, text="ИИшка периодически ищет обновления по выбранным темам, сохраняет конспекты и источники в базу знаний, а при подключённом облаке шифрует и синхронизирует их с Supabase. Это пополнение внешней базы знаний, а не переобучение весов нейросети.", style="MutedPanel.TLabel", wraplength=900).pack(anchor="w")
        self.research_auto_var = tk.BooleanVar(value=bool(self.config.get("research_auto_enabled", True)))
        self._make_checkbox(auto, "Включить фоновое исследование по расписанию (рекомендуется)", self.research_auto_var, background_key="panel").pack(anchor="w", pady=(8, 4))
        self.research_topics_box = tk.Text(auto, height=4, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, padx=9, pady=8, font=(self.font_family, 9))
        self.research_topics_box.pack(fill="x", pady=(2, 8))
        self.research_topics_box.insert("1.0", str(self.config.get("research_topics", "")))
        auto_row = ttk.Frame(auto, style="Panel.TFrame")
        auto_row.pack(fill="x")
        ttk.Label(auto_row, text="Интервал", style="Panel.TLabel").pack(side="left")
        self.research_interval_var = tk.StringVar(value=str(self.config.get("research_interval_hours", 3)))
        ttk.Combobox(auto_row, textvariable=self.research_interval_var, state="readonly", width=7, values=["1", "3", "6", "12", "24", "48"]).pack(side="left", padx=(6, 14))
        ttk.Button(auto_row, text="Сохранить настройки исследования", command=self.save_research_settings).pack(side="left")

        library = ttk.LabelFrame(content, text="База знаний · локальный кеш и облачная копия", padding=12)
        library.pack(fill="both", expand=True, pady=(0, 10))
        ttk.Label(library, text="Основная зашифрованная копия может храниться в Supabase; небольшой локальный кеш нужен для быстрых ответов и работы без сети. Источники могут устаревать — смотри дату получения и открывай исходную страницу.", style="MutedPanel.TLabel", wraplength=900).pack(anchor="w")
        list_frame = ttk.Frame(library, style="Panel.TFrame")
        list_frame.pack(fill="both", expand=True, pady=(8, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.research_list = tk.Listbox(list_frame, height=7, relief="flat", borderwidth=0, highlightthickness=0, activestyle="none", font=(self.font_family, 9))
        research_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.research_list.yview)
        self.research_list.configure(yscrollcommand=research_scroll.set)
        self.research_list.grid(row=0, column=0, sticky="nsew")
        research_scroll.grid(row=0, column=1, sticky="ns")
        self.research_list.bind("<<ListboxSelect>>", self._show_selected_research)
        self.research_preview = tk.Text(library, height=7, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, padx=9, pady=8, font=(self.font_family, 9), state="disabled")
        self.research_preview.pack(fill="x", pady=(0, 8))
        library_actions = ttk.Frame(library, style="Panel.TFrame")
        library_actions.pack(fill="x")
        ttk.Button(library_actions, text="Открыть источник в браузере", command=self.open_selected_research_source).pack(side="left")
        ttk.Button(library_actions, text="Удалить выбранный", command=self.delete_selected_research).pack(side="left", padx=8)
        ttk.Button(library_actions, text="Очистить базу знаний", command=self.clear_research_library).pack(side="left")
        ttk.Button(library_actions, text="Открыть папку данных", command=self.open_data_folder).pack(side="right")
        self._refresh_research_list()

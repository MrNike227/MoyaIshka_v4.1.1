# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class UpdateInterfaceMixin:
    def open_updates_folder(self) -> None:
        try:
            folder = self._updates_directory()
            folder.mkdir(parents=True, exist_ok=True)
            self._open_local_folder(folder)
        except Exception as exc:
            messagebox.showerror("Папка Updates", f"Не удалось открыть папку предложений.\n\n{exc}")

    def apply_improvement(self) -> None:
        patch = self.patch_preview.get("1.0", "end").strip()
        relative = self.improve_target_var.get().strip()
        generated_target = str(getattr(self, "pending_patch_target", "") or "").strip()
        if generated_target and generated_target != relative:
            messagebox.showwarning(
                "Саморазвитие",
                f"Этот Diff был подготовлен для {generated_target}. Выбери исходный файл перед применением.",
            )
            return
        if not patch:
            messagebox.showwarning("Саморазвитие", "Сначала подготовь или загрузи diff.")
            return
        try:
            if len(split_multi_file_unified_diff(patch)) > 1:
                messagebox.showwarning(
                    "Многофайловое изменение",
                    "Нельзя применить пакет к исходникам напрямую. Сохрани его в Updates и проверь полный набор файлов в Windows Sandbox. После успешной проверки изменения можно перенести отдельным подтверждаемым PR.",
                )
                return
        except ValueError as exc:
            messagebox.showerror("Саморазвитие", f"Diff не прошёл проверку: {exc}")
            return
        if not messagebox.askyesno(
            "Подтвердить изменение кода",
            f"Применить изменения к {relative}?\n\nПеред заменой создастся резервная копия. Будет проверен синтаксис и запущены тесты, если доступна среда Python. При ошибке тестов исходный файл будет восстановлен.\n\nВажно: тесты запускаются с правами текущей учётной записи Windows и не изолированы от остальных файлов и сети. Применяй и тестируй только доверенный diff.",
        ):
            return
        try:
            backup = apply_patch_with_backup(relative, patch, run_tests=True)
            self.improve_status_var.set(f"Изменение применено. Резервная копия: {backup}")
            messagebox.showinfo("Саморазвитие", f"Изменения успешно применены.\nРезервная копия:\n{backup}\n\nЕсли менялся main.py, перезапусти приложение.")
        except Exception as exc:
            messagebox.showerror("Не удалось применить изменение", str(exc))
            self.improve_status_var.set("Изменение отклонено или восстановлено.")

    # Updates are obtained from a user-configured GitHub Releases repository.
    def _selected_install_dir(self) -> Path:
        # The container is authoritative. A legacy install_dir must never override
        # the App folder after the user has selected/saved a container root.
        root = str(self.config.get("install_root_dir", "")).strip()
        if root:
            return resolve_install_layout(root)["app"]
        raw = str(self.config.get("install_dir", "")).strip()
        if raw:
            return resolve_install_dir(raw)
        running_exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
        return resolve_install_dir(running_exe=running_exe)

    def open_install_folder(self) -> None:
        """Open the App directory in the selected container."""
        try:
            root = self.update_install_dir_var.get().strip() if hasattr(self, "update_install_dir_var") else self.config.get("install_root_dir", "")
            folder = resolve_install_layout(root)["app"] if root else self._selected_install_dir()
            folder.mkdir(parents=True, exist_ok=True)
            self._open_local_folder(folder)
        except Exception as exc:
            messagebox.showerror("Папка App", f"Не удалось открыть папку приложения.\n\n{exc}")

    def open_update_log(self) -> None:
        """Open the updater's diagnostic log from the user-data directory."""
        log_path = DATA_DIR / "update.log"
        try:
            if not log_path.is_file():
                messagebox.showinfo(
                    "Журнал обновлений",
                    f"Журнал пока не создан. Он появится после первой попытки установки обновления.\n\nОжидаемое расположение:\n{log_path}",
                )
                return
            if os.name == "nt":
                subprocess.Popen(["notepad.exe", str(log_path)], close_fds=True)
            else:
                self._open_local_folder(log_path.parent)
        except Exception as exc:
            messagebox.showerror("Журнал обновлений", f"Не удалось открыть журнал.\n\n{exc}\n\nФайл:\n{log_path}")

    def browse_install_dir(self) -> None:
        current = Path(self.update_install_dir_var.get().strip() or default_install_root()).expanduser()
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Выбери корневую папку контейнера Моей ИИшки",
            initialdir=str(current),
            mustexist=False,
        )
        if selected:
            self.update_install_dir_var.set(str(Path(selected).resolve()))
            self.update_status_var.set("Корневая папка выбрана. App и Updates будут созданы внутри неё.")

    def save_update_settings(self, show_message: bool = True) -> None:
        try:
            root = ensure_install_dir_writable(self.update_install_dir_var.get().strip())
            layout = ensure_install_layout(root)
            current_app = Path(str(self.config.get("install_dir", ""))).expanduser().resolve() if self.config.get("install_dir") else None
            if current_app and (layout["updates"] == current_app or current_app in layout["updates"].parents):
                raise ValueError("Папка Updates оказалась внутри текущей установки. Выбери соседнюю папку-контейнер, чтобы обновлятор не удалил предложения.")
            ensure_install_dir_writable(layout["updates"])
            configure_temporary_storage(
                config={**self.config, "install_root_dir": str(root)},
                config_path=CONFIG_PATH,
                running_path=Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None,
                source_root=Path(__file__).resolve().parent,
            )
        except Exception as exc:
            messagebox.showerror("Папка контейнера", f"Не удалось использовать выбранную папку или её папку Temp.\n\n{exc}")
            return
        self.config["update_repo"] = self.update_repo_var.get().strip()
        self.config["auto_update_check"] = bool(self.auto_update_var.get())
        self.config["auto_cleanup_old_versions"] = bool(
            self.auto_cleanup_old_versions_var.get()
        )
        self.config["install_root_dir"] = str(root)
        self.config["updates_dir"] = str(layout["updates"])
        # The running legacy copy stays in place for this session; subsequent
        # updates target the saved container/App directory.
        self.update_install_dir_var.set(str(root))
        if hasattr(self, "actual_run_path_var"):
            current_run = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
            self.actual_run_path_var.set(
                f"Фактически запущена: {current_run}\nНовая папка App: {layout['app'] / 'ISH.exe'}\nПредложения: {layout['updates']}\nВременные файлы: {layout['root'] / 'Temp'}"
            )
        atomic_json_save(CONFIG_PATH, self.config)
        self.update_status_var.set(
            f"Контейнер сохранён. App: {layout['app']}; Updates: {layout['updates']}; временные файлы: {layout['root'] / 'Temp'}. "
            f"Текущая запущенная копия пока не перемещалась."
        )
        if show_message:
            messagebox.showinfo(
                "Контейнер сохранён",
                f"Корневая папка:\n{root}\n\nПапка приложения:\n{layout['app']}\nПапка предложений:\n{layout['updates']}\nПапка временных файлов:\n{layout['root'] / 'Temp'}\n\nЗагрузки и распаковка обновлений, временные файлы саморазвития, голоса и песочницы будут храниться в Temp. Текущая запущенная копия пока не перемещалась.",
            )

    def install_current_build_to_selected_folder(self) -> None:
        """Move the complete onedir folder into Container/App using the verified installer."""
        previous_values = {
            key: self.config.get(key)
            for key in ("install_root_dir", "updates_dir", "install_dir", "install_dir_user_selected")
        }
        staged_dir: Path | None = None
        try:
            root = ensure_install_dir_writable(self.update_install_dir_var.get().strip())
            layout = ensure_install_layout(root)
            current_app = Path(str(self.config.get("install_dir", ""))).expanduser().resolve() if self.config.get("install_dir") else None
            if current_app and (layout["updates"] == current_app or current_app in layout["updates"].parents):
                raise ValueError("Папка Updates оказалась внутри текущей установки. Выбери соседнюю папку-контейнер, чтобы обновлятор не удалил предложения.")
            ensure_install_dir_writable(layout["updates"])
            destination = ensure_install_dir_writable(layout["app"])
            configure_temporary_storage(
                config={**self.config, "install_root_dir": str(root)},
                config_path=CONFIG_PATH,
                running_path=Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None,
                source_root=Path(__file__).resolve().parent,
            )

            if not getattr(sys, "frozen", False):
                self.config["install_root_dir"] = str(root)
                self.config["updates_dir"] = str(layout["updates"])
                self.config["install_dir"] = str(destination)
                self.config["install_dir_user_selected"] = True
                atomic_json_save(CONFIG_PATH, self.config)
                self.update_status_var.set(
                    f"Контейнер настроен. App: {destination}. Updates: {layout['updates']}."
                )
                messagebox.showinfo(
                    "Контейнер сохранён",
                    "Сейчас приложение запущено из исходников. Переносить готовую сборку нечего.\n\n"
                    f"Папка для будущей установки:\n{destination}\n\n"
                    f"Папка самоанализа:\n{layout['updates']}",
                )
                return

            current_dir = Path(sys.executable).resolve().parent
            if current_dir == destination:
                self.config["install_root_dir"] = str(root)
                self.config["updates_dir"] = str(layout["updates"])
                self.config["install_dir"] = str(destination)
                self.config["install_dir_user_selected"] = True
                atomic_json_save(CONFIG_PATH, self.config)
                self.update_status_var.set(f"Приложение уже установлено в {destination}")
                messagebox.showinfo("Установка", "Программа уже находится в App выбранного контейнера.")
                return

            # Validate the current installation before prompting or changing settings.
            validate_app_directory(current_dir, APP_VERSION)
            if not messagebox.askyesno(
                "Переместить приложение",
                "Будет скопирована вся папка приложения, включая _internal и DLL.\n\n"
                f"Новая папка App:\n{destination}\n\n"
                f"Папка Updates останется отдельно:\n{layout['updates']}\n\n"
                "Старая установка останется на месте как резервная копия. "
                "После проверки новая копия запустится автоматически. Продолжить?",
            ):
                return

            staging_root = get_temp_directory(
                "update_staging",
                config={**self.config, "install_root_dir": str(root)},
                config_path=CONFIG_PATH,
            )
            staging_root.mkdir(parents=True, exist_ok=True)
            staged_dir = staging_root / f"ISH_install_{uuid.uuid4().hex}"
            shutil.copytree(current_dir, staged_dir)
            validate_app_directory(staged_dir, APP_VERSION)

            # Persist the new target only after explicit confirmation and successful staging.
            self.config["install_root_dir"] = str(root)
            self.config["updates_dir"] = str(layout["updates"])
            self.config["install_dir"] = str(destination)
            self.config["install_dir_user_selected"] = True
            atomic_json_save(CONFIG_PATH, self.config)

            try:
                launch_windows_directory_replacement(
                    staged_app_dir=staged_dir,
                    target_dir=destination,
                    parent_pid=os.getpid(),
                    log_path=DATA_DIR / "update.log",
                    expected_version=APP_VERSION,
                    receipt_path=get_temp_directory("updates") / "update_confirmation.json",
                    staged_verified=True,
                )
            except Exception:
                for key, value in previous_values.items():
                    if value is None:
                        self.config.pop(key, None)
                    else:
                        self.config[key] = value
                atomic_json_save(CONFIG_PATH, self.config)
                raise

            self.update_status_var.set(
                f"Перенос всей папки передан установщику. App: {destination}. Updates сохранён: {layout['updates']}"
            )
            if self.avatar is not None:
                self.avatar.hide()
            self.on_close()
        except Exception as exc:
            if staged_dir is not None and staged_dir.exists():
                shutil.rmtree(staged_dir, ignore_errors=True)
            messagebox.showerror(
                "Установка",
                f"Текущая версия не затронута. Проверь установленную onedir-сборку {APP_VERSION}.\n\n{exc}",
            )

    def search_old_versions(self) -> None:
        """Scan common user folders for obsolete/staged ISH executables."""
        self.update_status_var.set("Ищу старые копии ISH и MoyaIshka в известных папках пользователя и рядом с установкой…")

        def worker() -> None:
            try:
                running_exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
                results = scan_application_copies(
                    configured_install_dir=self.config.get("install_dir") or self._selected_install_dir(),
                    current_exe=running_exe,
                    data_dir=DATA_DIR,
                )
                self.events.put(("old_versions_scan_complete", results))
            except Exception as exc:
                self.events.put(("old_versions_scan_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _show_old_versions_window(self, results: list[dict[str, Any]]) -> None:
        """Show detected copies and require explicit selection before deletion."""
        window = tk.Toplevel(self.root)
        window.title("Поиск устаревших версий Моей ИИшки")
        window.geometry("940x500")
        window.minsize(760, 380)
        window.transient(self.root)
        window.configure(bg=self.colors.get("bg", "#101827"))

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Найденные копии приложения",
            style="PageTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Текущая запущенная копия исключена. Поиск охватывает ISH и MoyaIshka, включая старые папки установки. Удаление выполняется только для распознанных копий в известных местах, весь диск не сканируется.",
            style="MutedPanel.TLabel",
            wraplength=880,
        ).pack(anchor="w", pady=(4, 12))

        columns = ("version", "category", "size", "modified")
        tree = ttk.Treeview(outer, columns=columns, show="headings", selectmode="extended", height=11)
        tree.heading("version", text="Версия по имени папки")
        tree.heading("category", text="Расположение")
        tree.heading("size", text="Размер")
        tree.heading("modified", text="Изменён")
        tree.column("version", width=145, anchor="w")
        tree.column("category", width=230, anchor="w")
        tree.column("size", width=100, anchor="e")
        tree.column("modified", width=145, anchor="center")
        tree.pack(fill="both", expand=True)
        path_var = tk.StringVar(value="Выбери строку, чтобы увидеть полный путь.")
        path_entry = ttk.Entry(outer, textvariable=path_var, state="readonly")
        path_entry.pack(fill="x", pady=(9, 8))
        item_map: dict[str, dict[str, Any]] = {}

        def fill_rows(items: list[dict[str, Any]]) -> None:
            tree.delete(*tree.get_children())
            item_map.clear()
            for index, item in enumerate(items):
                iid = str(index)
                size = int(item.get("size", 0))
                size_text = f"{size / (1024 * 1024):.1f} МБ" if size >= 1024 * 1024 else f"{size / 1024:.0f} КБ"
                tree.insert("", "end", iid=iid, values=(item.get("version", "Не определена"), item.get("category", "Копия"), size_text, item.get("modified", "")))
                item_map[iid] = item
            if not items:
                path_var.set("Старые копии не найдены. Текущая программа не отображается в результатах.")
            else:
                path_var.set(f"Найдено копий: {len(items)}. Выбери одну или несколько строк.")

        def on_select(_event=None) -> None:
            selected = tree.selection()
            if len(selected) == 1:
                path_var.set(str(item_map[selected[0]].get("path", "")))
            elif selected:
                path_var.set(f"Выбрано файлов: {len(selected)}")
            elif results:
                path_var.set(f"Найдено копий: {len(results)}. Выбери одну или несколько строк.")

        def open_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Открыть расположение", "Сначала выбери файл.", parent=window)
                return
            path = Path(str(item_map[selected[0]]["path"]))
            try:
                if os.name == "nt":
                    subprocess.Popen(["explorer", f"/select,{path}"])
                else:
                    self._open_local_folder(path.parent)
            except Exception as exc:
                messagebox.showerror("Открыть расположение", str(exc), parent=window)

        def delete_selected() -> None:
            selected = list(tree.selection())
            if not selected:
                messagebox.showinfo("Удаление копий", "Сначала выбери файлы для удаления.", parent=window)
                return
            paths = [str(item_map[iid]["path"]) for iid in selected]
            preview = "\n".join(paths[:8])
            if len(paths) > 8:
                preview += f"\n… и ещё {len(paths) - 8} файлов"
            if not messagebox.askyesno(
                "Подтверждение удаления",
                "Удалить выбранные копии Моей ИИшки? Для распознанной onedir-установки будет удалена вся папка программы; отдельный EXE удаляется без посторонних файлов. Настройки и история чатов остаются нетронутыми.\n\n" + preview,
                parent=window,
            ):
                return
            removed = 0
            errors: list[str] = []
            active_exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
            for path in paths:
                try:
                    delete_application_copy(path, current_exe=active_exe)
                    removed += 1
                except Exception as exc:
                    errors.append(f"{path}: {exc}")
            fresh = scan_application_copies(
                configured_install_dir=self.config.get("install_dir") or self._selected_install_dir(),
                current_exe=active_exe,
                data_dir=DATA_DIR,
            )
            fill_rows(fresh)
            if errors:
                messagebox.showwarning(
                    "Результат удаления",
                    f"Удалено файлов: {removed}. Не удалось удалить: {len(errors)}.\n\n" + "\n".join(errors[:5]),
                    parent=window,
                )
            else:
                messagebox.showinfo("Результат удаления", f"Удалено файлов: {removed}.", parent=window)
            self.update_status_var.set(f"Поиск завершён. Удалено старых копий: {removed}.")

        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<Double-1>", lambda _e: open_selected())
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Открыть расположение", command=open_selected).pack(side="left")
        ttk.Button(buttons, text="Удалить выбранные", command=delete_selected).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Повторить поиск", command=lambda: self._rescan_old_versions_in_window(window, fill_rows)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Закрыть", command=window.destroy).pack(side="right")
        fill_rows(results)
        window.grab_set()

    def _rescan_old_versions_in_window(self, window: tk.Toplevel, fill_rows) -> None:
        window.configure(cursor="watch")
        def worker() -> None:
            try:
                running_exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
                items = scan_application_copies(
                    configured_install_dir=self.config.get("install_dir") or self._selected_install_dir(),
                    current_exe=running_exe,
                    data_dir=DATA_DIR,
                )
                self.events.put(("old_versions_rescan_complete", (window, fill_rows, items)))
            except Exception as exc:
                self.events.put(("old_versions_rescan_error", (window, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def _maybe_check_updates(self) -> None:
        if bool(self.config.get("auto_update_check", True)) and str(self.config.get("update_repo", "")).strip():
            self.check_for_updates(silent=True)

    def check_for_updates(self, silent: bool = False) -> None:
        repo = self.update_repo_var.get().strip() if hasattr(self, "update_repo_var") else str(self.config.get("update_repo", "")).strip()
        if not repo:
            if not silent:
                messagebox.showinfo("Обновления", "Укажи GitHub-репозиторий в формате владелец/название и сохрани настройки.")
            return
        self.update_status_var.set("Проверяю GitHub Releases…")

        def worker() -> None:
            try:
                info = check_latest_release(repo, APP_VERSION)
                self.events.put(("update_check", info))
            except Exception as exc:
                if not silent:
                    self.events.put(("update_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _download_update_worker(self, info: dict[str, Any]) -> None:
        try:
            path = download_verified_update(info, get_temp_directory("update_staging", config=self.config, config_path=CONFIG_PATH))
            self.events.put(("update_downloaded", {"path": str(path), "version": str(info.get("version", ""))}))
        except Exception as exc:
            self.events.put(("update_error", str(exc)))

    def _start_staged_update_install(
        self,
        install_dir: str | Path | None = None,
        *,
        source_process: bool = False,
    ) -> None:
        """Share the confirmed onedir install path for source and frozen launches."""
        staged = self.staged_update_path
        if not staged or not staged.is_file():
            messagebox.showerror("Обновление", "Проверенный EXE обновления не найден. Проверь обновления ещё раз.")
            return
        try:
            requested = Path(install_dir).expanduser().resolve() if install_dir else None
            configured_root = str(self.config.get("install_root_dir", "")).strip()
            if configured_root:
                container_root = Path(configured_root).expanduser().resolve()
            elif requested and requested.name.casefold() == "app":
                container_root = requested.parent
            elif requested:
                # Compatibility with older callers: a selected directory is the
                # container root, never the application folder itself.
                container_root = requested
            else:
                container_root = default_install_root(
                    legacy_install_dir=self.config.get("install_dir"),
                    running_exe=Path(sys.executable) if getattr(sys, "frozen", False) else None,
                )
            layout = ensure_install_layout(container_root)
            destination = ensure_install_dir_writable(layout["app"])
            ensure_install_dir_writable(layout["updates"])
            self.config["install_root_dir"] = str(layout["root"])
            self.config["updates_dir"] = str(layout["updates"])
            self.config["install_dir"] = str(destination)
            self.config["install_dir_user_selected"] = True
            atomic_json_save(CONFIG_PATH, self.config)
            configure_temporary_storage(
                config=self.config,
                config_path=CONFIG_PATH,
                running_path=Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None,
                source_root=Path(__file__).resolve().parent,
            )
            if source_process and hasattr(self, "update_install_dir_var"):
                self.update_install_dir_var.set(str(destination))

            launch_windows_directory_replacement(
                staged_app_dir=staged.parent,
                target_dir=destination,
                parent_pid=os.getpid(),
                log_path=DATA_DIR / "update.log",
                expected_version=self.staged_update_version,
                receipt_path=get_temp_directory("updates") / "update_confirmation.json",
                # download_verified_update validates the extracted manifest;
                # the detached helper validates it again immediately before install.
                staged_verified=True,
            )
            if source_process:
                self.update_status_var.set(
                    f"Передаю замену папки установщику. Резервная копия: {destination}.previous"
                )
            else:
                self.update_status_var.set(
                    f"Обновление устанавливается в {destination}. При сбое предыдущая версия будет восстановлена."
                )
            if self.avatar is not None:
                self.avatar.hide()
            self.on_close()
        except Exception as exc:
            if source_process:
                messagebox.showerror(
                    "Не удалось установить обновление",
                    f"Текущая версия не затронута.\n\nПричина: {exc}\n\nПакет сохранён здесь:\n{staged.parent}",
                )
            else:
                messagebox.showerror("Обновление", f"Текущая версия продолжает работать.\n\n{exc}")

    def _install_staged_update_from_source(self, install_dir: str | Path | None = None) -> None:
        self._start_staged_update_install(install_dir, source_process=True)

    def _apply_staged_update(self, install_dir: str | Path | None = None) -> None:
        self._start_staged_update_install(install_dir, source_process=False)

    # ---------- memory ----------


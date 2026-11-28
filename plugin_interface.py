# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class PluginInterfaceMixin:
    def _updates_directory(self) -> Path:
        return resolve_updates_directory(
            configured_updates_dir=self.config.get("updates_dir"),
            install_root=self.config.get("install_root_dir"),
            app_dir=self.config.get("install_dir"),
            data_dir=DATA_DIR,
        )

    def _open_local_folder(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Открыть папку", str(exc))

    def _open_url(self, url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    # Skills and plugin management.
    def _refresh_skill_list(self) -> None:
        if not hasattr(self, "skill_list"):
            return
        self.skill_list.delete(0, "end")
        self._skill_items = self.plugin_manager.list_skills()
        for item in self._skill_items:
            state = "ВКЛ" if item.get("enabled", True) else "ВЫКЛ"
            self.skill_list.insert("end", f"[{state}] {item.get('name', 'Без названия')} — {item.get('trigger', '')}")
        files = sorted(p.name for p in self.plugin_manager.plugins_dir.glob("*.py"))
        self.plugin_list_var.set("Файлы плагинов: " + (", ".join(files) if files else "пока нет"))

    def create_skill(self) -> None:
        name = simpledialog.askstring("Новый навык", "Название навыка:", parent=self.root)
        if not name or not name.strip():
            return
        trigger = simpledialog.askstring("Новый навык", "Когда ИИ должен применять этот навык?", parent=self.root) or ""
        instructions = simpledialog.askstring("Новый навык", "Что должен делать ИИ? Введи подробную инструкцию:", parent=self.root)
        if not instructions or not instructions.strip():
            return
        try:
            path = self.plugin_manager.create_skill(name, trigger, instructions)
            self._refresh_skill_list()
            self._set_status(f"Навык создан: {path.name}")
        except Exception as exc:
            messagebox.showerror("Создание навыка", str(exc))

    def toggle_selected_skill(self) -> None:
        selected = self.skill_list.curselection()
        if not selected:
            return
        item = self._skill_items[selected[0]]
        try:
            self.plugin_manager.set_skill_enabled(item["_file"], not bool(item.get("enabled", True)))
            self._refresh_skill_list()
            self._set_status("Состояние навыка изменено")
        except Exception as exc:
            messagebox.showerror("Навык", str(exc))

    def delete_selected_skill(self) -> None:
        selected = self.skill_list.curselection()
        if not selected:
            return
        item = self._skill_items[selected[0]]
        if not messagebox.askyesno("Удалить навык", f"Удалить навык «{item.get('name')}»?"):
            return
        try:
            self.plugin_manager.delete_skill(item["_file"])
            self._refresh_skill_list()
        except Exception as exc:
            messagebox.showerror("Удаление навыка", str(exc))

    def create_python_plugin(self) -> None:
        name = simpledialog.askstring("Создать плагин", "Имя плагина (латиница):", parent=self.root)
        if not name:
            return
        try:
            path = self.plugin_manager.create_python_plugin_template(name)
            self._refresh_skill_list()
            messagebox.showinfo("Шаблон создан", f"Файл создан:\n{path}\n\nОткрой его в редакторе и настрой функцию handle_command().")
            if os.name == "nt":
                subprocess.Popen(["notepad.exe", str(path)], shell=False)
        except Exception as exc:
            messagebox.showerror("Создание плагина", str(exc))

    def _toggle_python_plugins(self) -> None:
        enabled = bool(self.python_plugins_var.get())
        if enabled and not messagebox.askyesno(
            "Разрешить выполнение Python-плагинов?",
            "ВНИМАНИЕ: Python-плагины не изолированы. Любой включённый файл может выполнять код с правами вашей учётной записи Windows. Включайте только полностью проверенный код. Продолжить?",
        ):
            self.python_plugins_var.set(False)
            enabled = False
        self.plugin_manager.enabled_python = enabled
        self.config["plugins_enabled"] = enabled
        atomic_json_save(CONFIG_PATH, self.config)
        self._set_status("Python-плагины разрешены" if enabled else "Python-плагины выключены")



# -*- coding: utf-8 -*-
"""Memory controls and editing methods for ISHApp."""
from __future__ import annotations

class MemoryInterfaceMixin:
    def _toggle_auto_memory(self) -> None:
        self.config["auto_memory"] = bool(self.auto_memory_var.get())
        atomic_json_save(CONFIG_PATH, self.config)
        self._set_status("Автоматическая память включена" if self.config["auto_memory"] else "Автоматическая память выключена")

    def _toggle_memory_semantic(self) -> None:
        self.config["memory_semantic_enabled"] = bool(self.memory_semantic_var.get())
        atomic_json_save(CONFIG_PATH, self.config)
        self._schedule_cloud_sync()
        state = "включён" if self.config["memory_semantic_enabled"] else "выключен"
        self._set_status(f"Семантический поиск {state}")

    def save_memory_semantic_settings(self) -> None:
        model = self.memory_embedding_model_var.get().strip()
        if not model or len(model) > 120 or not re.fullmatch(r"[A-Za-z0-9._:/-]+", model):
            messagebox.showerror("Память ИИ", "Укажи корректное имя локальной модели Ollama.")
            return
        self.config["memory_embedding_model"] = model
        self.config["memory_semantic_enabled"] = bool(self.memory_semantic_var.get())
        atomic_json_save(CONFIG_PATH, self.config)
        self._schedule_cloud_sync()
        self._set_status(f"Модель смыслового поиска сохранена: {model}")


    def _refresh_memory_list(self) -> None:
        if not hasattr(self, "memory_list"):
            return
        self.memory_list.delete(0, "end")
        memories, metadata = normalize_memory_metadata(
            self.config.get("memory", []), self.config.get("memory_metadata", [])
        )
        self.config["memory"] = memories
        self.config["memory_metadata"] = metadata
        active_count = 0
        for index, (item, record) in enumerate(zip(memories, metadata), 1):
            state = str(record.get("status", "active"))
            if state == "active":
                active_count += 1
            marker = " · заменено" if state == "superseded" else " · срок истёк" if state == "expired" else ""
            display = f"{index:02d}. [{record.get('category', 'Факты')} · {record.get('importance', 3)}/5{marker}] {str(item).replace(chr(10), ' ')}"
            if len(display) > 170:
                display = display[:167] + "…"
            self.memory_list.insert("end", display)
        if hasattr(self, "memory_count_var"):
            self.memory_count_var.set(f"{active_count} активных из {len(memories)} записей · поиск по смыслу работает локально")

    def add_memory(self) -> None:
        text = self.memory_entry_var.get().strip()
        if not text:
            return
        memories, metadata, action = add_or_update_memory(
            self.config.get("memory", []), self.config.get("memory_metadata", []), text, source="manual"
        )
        if action == "blocked":
            messagebox.showwarning("Память ИИ", "Эта запись похожа на пароль, ключ, контакт или чувствительные данные. Такие сведения не сохраняются.")
            return
        if action == "duplicate":
            messagebox.showinfo("Память ИИ", "Такая запись уже есть. Её актуальность обновлена.")
        elif action == "superseded":
            self._set_status("Новая запись заменила противоречащее предпочтение или цель")
        self.config["memory"] = memories
        self.config["memory_metadata"] = metadata
        atomic_json_save(CONFIG_PATH, self.config)
        self.memory_entry_var.set("")
        self._refresh_memory_list()
        self._schedule_cloud_sync()
        if action != "superseded":
            self._set_status("Запись добавлена в интеллектуальную память")

    def edit_memory(self) -> None:
        selected = self.memory_list.curselection()
        if not selected:
            return
        index = selected[0]
        items = self.config.get("memory", [])
        if index >= len(items):
            return
        value = simpledialog.askstring("Изменить запись памяти", "Текст записи:", initialvalue=items[index], parent=self.root)
        if value and value.strip():
            memories, metadata, action = edit_memory_record(
                items, self.config.get("memory_metadata", []), index, value.strip()
            )
            if action == "blocked":
                messagebox.showwarning("Память ИИ", "Пароли, ключи, контакты и чувствительные данные не сохраняются.")
                return
            if action == "duplicate":
                messagebox.showinfo("Память ИИ", "Такая запись уже существует.")
                return
            self.config["memory"] = memories
            self.config["memory_metadata"] = metadata
            atomic_json_save(CONFIG_PATH, self.config)
            self._refresh_memory_list()
            self.memory_list.selection_set(index)
            self._schedule_cloud_sync()
            self._set_status("Запись памяти изменена")

    def remove_memory(self) -> None:
        selected = self.memory_list.curselection()
        if not selected:
            return
        index = selected[0]
        items = self.config.get("memory", [])
        metadata = self.config.get("memory_metadata", [])
        if 0 <= index < len(items):
            del items[index]
            if isinstance(metadata, list) and index < len(metadata):
                del metadata[index]
            self.config["memory"] = items
            self.config["memory_metadata"] = metadata
            atomic_json_save(CONFIG_PATH, self.config)
            self._refresh_memory_list()
            self._schedule_cloud_sync()
            self._set_status("Запись удалена из памяти")

    def clear_memory(self) -> None:
        if not self.config.get("memory"):
            return
        if messagebox.askyesno("Очистить память", "Удалить все записи памяти и их категории? История чатов останется."):
            self.config["memory"] = []
            self.config["memory_metadata"] = []
            atomic_json_save(CONFIG_PATH, self.config)
            self._refresh_memory_list()
            self._schedule_cloud_sync()
            self._set_status("Интеллектуальная память очищена")

    # ---------- utilities ----------


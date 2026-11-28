# -*- coding: utf-8 -*-
"""Online and local model connection checks and controls."""
from __future__ import annotations

class ModelSettingsMixin:
    def test_online(self) -> None:
        if not self.api_key_var.get().strip():
            messagebox.showwarning("Нет API-ключа", "Сначала укажите API-ключ в настройках.")
            return
        settings = {"online_url": self.online_url_var.get().strip(), "online_model": self.online_model_var.get().strip(), "api_key": self.api_key_var.get().strip(), "temperature": 0.2}
        self._set_status("Проверяю онлайн API…")
        def worker() -> None:
            try:
                answer = self._call_online(settings, [{"role": "user", "content": "Ответь одним словом: подключение работает."}])
                self.events.put(("test_result", ("Онлайн-подключение", True, "API ответил успешно.\n\n" + answer[:300])))
            except Exception as exc:
                self.events.put(("test_result", ("Онлайн-подключение", False, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def test_ollama(self) -> None:
        base = normalize_url(self.ollama_url_var.get())
        wanted = self.ollama_model_var.get().strip()
        self._set_status("Проверяю Ollama…")
        def worker() -> None:
            try:
                request = urllib.request.Request(base + "/api/tags", headers={"User-Agent": f"ISH/{APP_VERSION}"})
                with urllib.request.urlopen(request, timeout=8) as response:
                    data = json.loads(response.read().decode("utf-8", errors="replace"))
                models = [str(model.get("name", "")) for model in data.get("models", []) if isinstance(model, dict)]
                found = any(name == wanted or name.startswith(wanted + ":") or wanted.startswith(name + ":") for name in models)
                if found:
                    result = ("Ollama", True, f"Ollama работает. Модель «{wanted}» найдена.")
                else:
                    text = "Ollama запущена, но указанная модель не найдена.\n\nУстановленные модели:\n" + ("\n".join(models) if models else "Пока нет моделей.") + f"\n\nЗагрузить: ollama pull {wanted}"
                    result = ("Ollama", False, text)
            except Exception as exc:
                result = ("Ollama", False, f"Не удалось подключиться к Ollama: {exc}\n\nУстановите и запустите Ollama.")
            self.events.put(("test_result", result))
        threading.Thread(target=worker, daemon=True).start()

    def copy_ollama_command(self) -> None:
        model = self.ollama_model_var.get().strip()
        if not model:
            return
        command = f"ollama pull {model}"
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self._set_status("Команда загрузки модели скопирована")

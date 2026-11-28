import json
import os
import tempfile
import unittest
import queue
from pathlib import Path

os.environ.setdefault("APPDATA", tempfile.mkdtemp(prefix="moya_test_appdata_"))

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as main_module
import chat_interface
import research_interface
from conversation_store import Store as ConversationStore
from main import DEFAULT_CONFIG, ISHApp, Store, extract_openai_content, read_attachment


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.store = Store(self.db_path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_main_keeps_store_compatibility_alias(self):
        self.assertIs(Store, ConversationStore)

    def test_create_message_and_title(self):
        chat_id = self.store.create_conversation()
        self.store.add_message(chat_id, "user", "Привет, Ишка")
        self.store.add_message(chat_id, "assistant", "Привет!")
        self.assertEqual(self.store.get_conversation(chat_id)["title"], "Привет, Ишка")
        self.assertEqual(len(self.store.get_messages(chat_id)), 2)

    def test_export_markdown(self):
        chat_id = self.store.create_conversation("Проверка")
        self.store.add_message(chat_id, "user", "Вопрос")
        self.store.add_message(chat_id, "assistant", "Ответ")
        markdown = self.store.export_markdown(chat_id)
        self.assertIn("# Проверка", markdown)
        self.assertIn("## Вы", markdown)
        self.assertIn("Ответ", markdown)

    def test_clear_and_delete(self):
        chat_id = self.store.create_conversation()
        self.store.add_message(chat_id, "user", "Удаляемое сообщение")
        self.store.clear_messages(chat_id)
        self.assertEqual(self.store.get_messages(chat_id), [])
        self.store.delete_conversation(chat_id)
        self.assertIsNone(self.store.get_conversation(chat_id))

    def test_conversation_ids_reads_sqlite_rows_by_column(self):
        first_id = self.store.create_conversation("Первый")
        second_id = self.store.create_conversation("Второй")
        self.assertEqual(self.store.conversation_ids(), {first_id, second_id})

    def test_import_legacy_history(self):
        history_path = Path(self.temp.name) / "history.json"
        history_path.write_text(json.dumps([
            {"role": "user", "content": "Старый вопрос"},
            {"role": "assistant", "content": "Старый ответ"},
        ], ensure_ascii=False), encoding="utf-8")
        self.store.import_legacy_history(history_path)
        chats = self.store.list_conversations()
        self.assertEqual(len(chats), 1)
        self.assertEqual(len(self.store.get_messages(chats[0]["id"])), 2)


class ParsingTests(unittest.TestCase):
    def test_cloud_merge_uses_sqlite_safe_conversation_id_helper(self):
        source = Path(__import__("cloud_interface").__file__).read_text(encoding="utf-8")
        self.assertIn("self.store.conversation_ids()", source)
        self.assertNotIn('str(c.get("id")) for c in self.store.list_conversations()', source)

    def test_extract_openai_content(self):
        self.assertEqual(extract_openai_content({"choices": [{"message": {"content": " Готово "}}]}), "Готово")

    def test_read_text_attachment(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "note.txt"
            path.write_text("Тестовый текст", encoding="utf-8")
            self.assertEqual(read_attachment(path), "Тестовый текст")

    def test_chat_improvement_ideas_are_connected_to_send_and_analysis(self):
        source = Path(chat_interface.__file__).read_text(encoding="utf-8")
        selfdev_source = Path(__import__("self_improvement_interface").__file__).read_text(encoding="utf-8")
        self.assertIn("save_chat_improvement_idea(", source)
        self.assertIn("load_chat_improvement_ideas(", selfdev_source)
        self.assertIn("идея сохранена для самоанализа", source)

    def test_attachment_size_is_limited(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.txt"
            path.write_text("я" * 45000, encoding="utf-8")
            text = read_attachment(path)
            self.assertLess(len(text), 45000)
            self.assertIn("Текст сокращён", text)


class KeyboardAndPrivacyTests(unittest.TestCase):
    def test_enter_sends_message(self):
        app = ISHApp.__new__(ISHApp)
        calls = []
        app.send_message = lambda: calls.append("sent")
        result = app._input_return(type("Event", (), {"state": 0})())
        self.assertEqual(result, "break")
        self.assertEqual(calls, ["sent"])

    def test_shift_enter_keeps_text_widget_newline(self):
        app = ISHApp.__new__(ISHApp)
        calls = []
        app.send_message = lambda: calls.append("sent")
        result = app._input_return(type("Event", (), {"state": 1})())
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_web_chat_returns_sources_without_api_key_or_ollama(self):
        app = ISHApp.__new__(ISHApp)
        app.config = {"research_results_limit": 3, "research_fetch_pages": 1}
        app.events = queue.Queue()
        app._call_ollama = lambda *_args: (_ for _ in ()).throw(ConnectionError("Ollama недоступна"))
        original_search = research_interface.search_and_fetch
        research_interface.search_and_fetch = lambda *_args, **_kwargs: [{
            "title": "Проверенная статья",
            "url": "https://example.com/article",
            "snippet": "Краткая выдержка из статьи",
            "content": "Подробный текст статьи для проверки веб-поиска без ключа.",
        }]
        try:
            app._web_chat_worker("тест", "Только онлайн", {"api_key": ""}, [
                {"role": "user", "content": "поищи тест"}
            ], "chat-1")
        finally:
            research_interface.search_and_fetch = original_search
        events = []
        while not app.events.empty():
            events.append(app.events.get_nowait())
        reply = next(payload for event, payload in events if event == "reply")
        self.assertEqual(reply[0], "chat-1")
        self.assertIn("Проверенная статья", reply[1])
        self.assertIn("https://example.com/article", reply[1])
        self.assertEqual(reply[2], "интернет · без API-ключа")

    def test_microphone_is_off_by_default(self):
        self.assertFalse(DEFAULT_CONFIG["microphone_enabled"])

    def test_background_research_is_enabled_for_413_profile(self):
        self.assertTrue(DEFAULT_CONFIG["research_auto_enabled"])
        self.assertTrue(DEFAULT_CONFIG["web_search_enabled"])
        self.assertIn("Искусственный интеллект", DEFAULT_CONFIG["research_topics"])
        self.assertEqual(DEFAULT_CONFIG["background_ram_limit_mb"], 5120)
        self.assertEqual(DEFAULT_CONFIG["background_min_available_ram_mb"], 8192)
        self.assertEqual(DEFAULT_CONFIG["research_results_limit"], 10)
        self.assertEqual(DEFAULT_CONFIG["research_fetch_pages"], 5)
        self.assertEqual(DEFAULT_CONFIG["research_interval_hours"], 3)
        self.assertTrue(DEFAULT_CONFIG["cloud_auto_sync"])



class SelfImprovementModelSelectionTests(unittest.TestCase):
    def _app(self):
        app = ISHApp.__new__(ISHApp)
        app.config = {
            "mode": "Только онлайн",
            "online_url": "https://api.example.test/v1/chat/completions",
            "online_model": "cloud-model",
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "local-model",
        }
        app.api_key = ""
        pressure = type("Pressure", (), {"system_pressure": False})()
        app.resource_governor = type(
            "Governor", (), {"snapshot": lambda _self: pressure}
        )()
        return app

    def test_self_analysis_uses_local_ollama_without_api_key_in_online_chat_mode(self):
        app = self._app()
        captured = {}

        def local_call(settings, messages):
            captured["settings"] = settings
            captured["messages"] = messages
            return "local self-analysis result"

        app._call_online = lambda *_args: self.fail("Online API must not be called without a key")
        app._call_ollama = local_call

        result = app._current_model_call([{"role": "user", "content": "Проверь код"}])

        self.assertEqual(result, "local self-analysis result")
        self.assertEqual(captured["settings"]["task_profile"], "self_improvement")
        self.assertEqual(captured["settings"]["api_key"], "")
        self.assertEqual(captured["settings"]["ollama_model"], "local-model")

    def test_self_analysis_keeps_online_model_when_api_key_is_configured(self):
        app = self._app()
        app.api_key = "test-api-key"
        app._call_online = lambda _settings, _messages: "online self-analysis result"
        app._call_ollama = lambda *_args: self.fail("Local model must not replace selected online model")

        result = app._current_model_call([{"role": "user", "content": "Проверь код"}])

        self.assertEqual(result, "online self-analysis result")

    def test_diff_regeneration_increases_model_temperature_gradually(self):
        app = self._app()
        temperatures = []
        app._call_ollama = lambda settings, _messages: (
            temperatures.append(settings["temperature"]) or "ok"
        )
        for attempt in range(3):
            self.assertEqual(
                app._current_model_call(
                    [{"role": "user", "content": "Подготовь diff"}],
                    generation_attempt=attempt,
                ),
                "ok",
            )
        self.assertEqual(temperatures, [0.15, 0.25, 0.35])


class OllamaSelfImprovementRecoveryTests(unittest.TestCase):
    def test_self_improvement_retries_on_cpu_after_llama_server_access_violation(self):
        from unittest.mock import patch
        calls = []

        def fake_post(_url, payload, timeout=None):
            calls.append(payload)
            if len(calls) == 1:
                raise RuntimeError(
                    'HTTP 500: {"error":"llama-server process has terminated: exit status 0xc0000005"}'
                )
            return {"message": {"content": "Проверка завершена"}, "done_reason": "stop"}

        settings = {
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "local-model",
            "task_profile": "self_improvement",
        }
        with patch.object(chat_interface, "post_json", side_effect=fake_post):
            result = ISHApp._call_ollama(
                settings, [{"role": "user", "content": "Проверь код"}]
            )

        self.assertEqual(result, "Проверка завершена")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["options"]["num_ctx"], 4096)
        self.assertEqual(calls[0]["options"]["num_batch"], 64)
        self.assertNotIn("num_gpu", calls[0]["options"])
        self.assertEqual(calls[1]["options"]["num_gpu"], 0)
        self.assertEqual(calls[1]["options"]["num_batch"], 32)

    def test_self_analysis_retries_once_with_repeat_penalty_after_token_loop(self):
        from unittest.mock import patch
        calls = []

        def fake_post(_url, payload, timeout=None):
            calls.append(payload)
            if len(calls) == 1:
                raise RuntimeError(
                    'HTTP 500: {"error":"prediction aborted, token repeat limit reached"}'
                )
            return {"message": {"content": '{"suggestions":[]}'}, "done_reason": "stop"}

        settings = {
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "local-model",
            "task_profile": "self_improvement",
            "temperature": 0.15,
        }
        messages = [{"role": "user", "content": "Проведи аудит кода"}]
        with patch.object(chat_interface, "post_json", side_effect=fake_post):
            result = ISHApp._call_ollama(settings, messages)

        self.assertEqual(result, '{"suggestions":[]}')
        self.assertEqual(len(calls), 2)
        first = calls[0]["options"]
        retry = calls[1]["options"]
        self.assertNotIn("repeat_penalty", first)
        self.assertEqual(retry["repeat_penalty"], 1.15)
        self.assertEqual(retry["repeat_last_n"], 128)
        self.assertEqual(retry["temperature"], 0.25)
        self.assertEqual(retry["num_predict"], 768)
        self.assertEqual(retry["num_batch"], 32)
        self.assertIn("не повторяй", calls[1]["messages"][-1]["content"].casefold())

    def test_repeated_token_error_after_retry_returns_clear_message(self):
        from unittest.mock import patch
        failure = RuntimeError(
            'HTTP 500: {"error":"prediction aborted, token repeat limit reached"}'
        )
        settings = {
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "local-model",
            "task_profile": "self_improvement",
        }
        with patch.object(chat_interface, "post_json", side_effect=failure) as post:
            with self.assertRaisesRegex(RuntimeError, "зациклилась на повторяющихся токенах"):
                ISHApp._call_ollama(
                    settings, [{"role": "user", "content": "Проведи аудит"}]
                )
        self.assertEqual(post.call_count, 2)

    def test_ordinary_chat_does_not_retry_after_token_repeat_limit(self):
        from unittest.mock import patch
        failure = RuntimeError(
            'HTTP 500: {"error":"prediction aborted, token repeat limit reached"}'
        )
        settings = {
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "local-model",
            "task_profile": "chat",
        }
        with patch.object(chat_interface, "post_json", side_effect=failure) as post:
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                ISHApp._call_ollama(
                    settings, [{"role": "user", "content": "Привет"}]
                )
        self.assertEqual(post.call_count, 1)

    def test_ordinary_chat_does_not_silently_switch_to_cpu_after_access_violation(self):
        from unittest.mock import patch
        failure = RuntimeError(
            'HTTP 500: {"error":"llama-server process has terminated: exit status 0xc0000005"}'
        )
        settings = {
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "local-model",
            "task_profile": "chat",
        }
        with patch.object(chat_interface, "post_json", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                ISHApp._call_ollama(
                    settings, [{"role": "user", "content": "Привет"}]
                )



class SelfImprovementInteractionTests(unittest.TestCase):
    class Clipboard:
        def __init__(self, value=""):
            self.value = value

        def clipboard_clear(self):
            self.value = ""

        def clipboard_append(self, value):
            self.value += str(value)

        def clipboard_get(self):
            if not self.value:
                raise main_module.tk.TclError("clipboard is empty")
            return self.value

        def update_idletasks(self):
            pass

    class Status:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    class ScrollView:
        def __init__(self, first=0.0, last=1.0):
            self.first = first
            self.last = last
            self.calls = []

        def yview(self):
            return self.first, self.last

        def yview_scroll(self, steps, _units):
            self.calls.append(steps)
            height = self.last - self.first
            self.first = max(0.0, min(1.0 - height, self.first + steps * 0.25))
            self.last = self.first + height

    def test_copy_selected_model_proposal_copies_only_proposed_text(self):
        app = ISHApp.__new__(ISHApp)
        app.root = self.Clipboard()
        app.improvement_listbox = type("List", (), {"curselection": lambda _self: (0,)})()
        app.improvement_suggestions = [{
            "title": "Улучшение",
            "problem": "Неудобно",
            "current": "Текущий вариант",
            "proposed": "Только предлагаемый текст",
            "benefit": "Удобнее",
        }]
        app.improve_status_var = self.Status()

        app.copy_selected_improvement()

        self.assertEqual(app.root.value, "Только предлагаемый текст")
        self.assertIn("скопирован", app.improve_status_var.value)

    def test_copy_improvement_task_copies_complete_task_text(self):
        app = ISHApp.__new__(ISHApp)
        app.root = self.Clipboard()
        app.improve_prompt_box = type(
            "Prompt", (), {"get": lambda _self, _start, _end: "  Создай резервное копирование  "}
        )()
        app.improve_status_var = self.Status()

        app.copy_improvement_task()

        self.assertEqual(app.root.value, "Создай резервное копирование")

    def test_paste_improvement_task_inserts_clipboard_text(self):
        class Prompt:
            def __init__(self):
                self.inserted = ""
                self.focused = False

            def delete(self, _start, _end):
                raise main_module.tk.TclError("no selection")

            def insert(self, _index, value):
                self.inserted += value

            def focus_set(self):
                self.focused = True

        app = ISHApp.__new__(ISHApp)
        app.root = self.Clipboard("Вставленный текст")
        app.improve_prompt_box = Prompt()
        app.improve_status_var = self.Status()

        app.paste_improvement_task()

        self.assertEqual(app.improve_prompt_box.inserted, "Вставленный текст")
        self.assertTrue(app.improve_prompt_box.focused)
        self.assertIn("вставлен", app.improve_status_var.value)

    def test_nested_text_scroll_hands_off_to_page_at_bottom_and_top(self):
        inner = self.ScrollView(first=0.0, last=0.5)
        page = self.ScrollView(first=0.0, last=0.4)
        scroll_down = type("Event", (), {"delta": -120, "num": 0})()
        scroll_up = type("Event", (), {"delta": 120, "num": 0})()

        self.assertEqual(
            ISHApp._scroll_nested_text(scroll_down, inner, page), "break"
        )
        self.assertEqual(inner.calls, [1])
        self.assertEqual(page.calls, [])

        inner.first, inner.last = 0.5, 1.0
        ISHApp._scroll_nested_text(scroll_down, inner, page)
        self.assertEqual(page.calls, [1])

        inner.first, inner.last = 0.5, 1.0
        ISHApp._scroll_nested_text(scroll_up, inner, page)
        self.assertEqual(inner.calls, [1, -1])

        inner.first, inner.last = 0.0, 0.5
        ISHApp._scroll_nested_text(scroll_up, inner, page)
        self.assertEqual(inner.calls, [1, -1])
        self.assertEqual(page.calls, [1, -1])

    def test_nested_text_scroll_supports_linux_wheel_buttons(self):
        inner = self.ScrollView(first=0.5, last=1.0)
        page = self.ScrollView()
        event = type("Event", (), {"delta": 0, "num": 4})()

        ISHApp._scroll_nested_text(event, inner, page)

        self.assertEqual(inner.calls, [-1])
        self.assertEqual(page.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

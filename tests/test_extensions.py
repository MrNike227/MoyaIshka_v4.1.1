import json
import os
import tempfile
import unittest
from pathlib import Path

from auto_memory import extract_memory_candidate
from plugin_manager import PluginManager
from self_improvement import apply_unified_diff, build_model_source_context, editable_project_files, extract_unified_diff, generate_validated_unified_diff, parse_improvement_suggestions, split_multi_file_unified_diff, apply_multi_file_unified_diff, generate_validated_multi_file_unified_diff, related_test_path
from updater import version_tuple
from updater_helper import install_from_source, _powershell_script, write_powershell_updater_script, user_install_dir, resolve_install_dir, ensure_install_dir_writable, scan_application_copies, delete_application_copy
from windows_control import handle_voice_command


class AutoMemoryTests(unittest.TestCase):
    def test_explicit_memory_phrase(self):
        self.assertEqual(extract_memory_candidate("Запомни: я предпочитаю тёмную тему"), "я предпочитаю тёмную тему")

    def test_explicit_preference(self):
        value = extract_memory_candidate("Я предпочитаю короткие ответы")
        self.assertIn("короткие ответы", value or "")

    def test_secret_is_not_saved(self):
        self.assertIsNone(extract_memory_candidate("Запомни: мой пароль 123456"))
        self.assertIsNone(extract_memory_candidate("Запомни: мой API key abc123"))

    def test_arbitrary_chat_is_not_saved(self):
        self.assertIsNone(extract_memory_candidate("Привет, как дела?"))


class PatchTests(unittest.TestCase):
    def test_large_source_context_contains_relevant_function_only(self):
        padding = "".join(f"# padding {index} " + ("x" * 80) + "\n" for index in range(1400))
        source = (
            "import os\n\n"
            + padding
            + "def update_profile():\n    return 'profile'\n\n"
            + "def erase_secret():\n    return 'secret'\n"
        )
        self.assertGreater(len(source), 90_000)
        context = build_model_source_context(source, "change the profile button")
        self.assertLessEqual(len(context), 90_000)
        self.assertIn("def update_profile", context)
        self.assertIn("исходные строки", context)
        self.assertNotIn("return 'secret'", context)

    def test_large_source_context_keeps_original_line_numbers_for_diff(self):
        padding = "".join(f"# padding {index} " + ("x" * 80) + "\n" for index in range(1400))
        source = "import os\n\n" + padding + "def update_profile():\n    return 'profile'\n"
        context = build_model_source_context(source, "profile")
        original_line = source.splitlines().index("    return 'profile'") + 1
        patch = (
            "--- a/main.py\n+++ b/main.py\n"
            + f"@@ -{original_line},1 +{original_line},1 @@\n"
            + "-    return 'profile'\n+    return 'PROFILE'\n"
        )
        updated = apply_unified_diff(source, patch, "main.py")
        self.assertIn("return 'PROFILE'", updated)

    def test_editable_file_scan_uses_project_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "tests" / "ISH"
            (root / "pkg").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / ".git" / "hooks").mkdir(parents=True)
            (root / ".github").mkdir()
            (root / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "pkg" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
            (root / "tests" / "test_module.py").write_text("VALUE = 3\n", encoding="utf-8")
            (root / ".git" / "hooks" / "hook.py").write_text("VALUE = 4\n", encoding="utf-8")
            (root / ".github" / "helper.py").write_text("VALUE = 5\n", encoding="utf-8")
            previous = os.environ.get("MOYA_PROJECT_DIR")
            os.environ["MOYA_PROJECT_DIR"] = str(root)
            try:
                self.assertEqual(editable_project_files(), ["main.py", "pkg/module.py"])
            finally:
                if previous is None:
                    os.environ.pop("MOYA_PROJECT_DIR", None)
                else:
                    os.environ["MOYA_PROJECT_DIR"] = previous

    def test_small_source_context_is_unchanged(self):
        source = "def answer():\n    return 42\n"
        self.assertEqual(build_model_source_context(source, "answer"), source)

    def test_extract_unified_diff_from_markdown_and_prose(self):
        original = "def answer():\n    return 1\n"
        fence = chr(96) * 3
        response = (
            "Изменение подготовлено:\n\n" + fence + "diff\n"
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,2 +1,2 @@\n def answer():\n-    return 1\n+    return 2\n"
            + fence + "\n"
        )
        patch = extract_unified_diff(response, "main.py")
        self.assertEqual(apply_unified_diff(original, patch, "main.py"), "def answer():\n    return 2\n")

    def test_extract_unified_diff_adds_missing_file_headers(self):
        original = "value = 1\n"
        response = "@@ -1 +1 @@\n-value = 1\n+value = 2\n"
        patch = extract_unified_diff(response, "module.py")
        self.assertEqual(apply_unified_diff(original, patch, "module.py"), "value = 2\n")

    def test_extract_unified_diff_rejects_other_file(self):
        response = "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-a\n+b\n"
        with self.assertRaises(ValueError):
            extract_unified_diff(response, "main.py")

    def test_extract_unified_diff_accepts_insertion_only_changes(self):
        original = "one\n two\n"
        response = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,0 +2 @@\n+inserted\n"
        )
        patch = extract_unified_diff(response, "main.py")
        self.assertEqual(
            apply_unified_diff(original, patch, "main.py"),
            "one\ninserted\n two\n",
        )

    def test_extract_unified_diff_accepts_deletion_only_changes(self):
        original = "remove me\nkeep me\n"
        response = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1 +0,0 @@\n-remove me\n"
        )
        patch = extract_unified_diff(response, "main.py")
        self.assertEqual(
            apply_unified_diff(original, patch, "main.py"),
            "keep me\n",
        )

    def test_extract_unified_diff_rejects_missing_hunk(self):
        with self.assertRaises(ValueError):
            extract_unified_diff("--- a/main.py\n+++ b/main.py\nизменений нет", "main.py")

    def test_apply_insertion_hunk_after_first_line(self):
        original = "one\ntwo\n"
        patch = "--- a/main.py\n+++ b/main.py\n@@ -1,0 +2 @@\n+inserted\n"
        self.assertEqual(apply_unified_diff(original, patch, "main.py"), "one\ninserted\ntwo\n")

    def test_patch_rejects_hunk_line_count_mismatch(self):
        patch = "--- a/main.py\n+++ b/main.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"
        with self.assertRaises(ValueError):
            apply_unified_diff("old\n", patch, "main.py")

    def test_parse_improvement_suggestions(self):
        response = (
            '{"suggestions":[{"title":"Обработка ошибок","problem":"Ошибка теряется",'
            '"current":"except: pass","proposed":"except OSError as exc: log(exc)",'
            '"benefit":"Проще найти причину"}]}'
        )
        items = parse_improvement_suggestions(response)
        self.assertEqual(len(items), 1)
        self.assertIn("Обработка ошибок", items[0]["title"])
        self.assertIn("log", items[0]["proposed"])

    def test_parse_improvement_suggestion_location(self):
        response = (
            '{"suggestions":[{"title":"Проверка URL","location":"main.py.ApiClient.fetch",'
            '"problem":"Нет проверки схемы","current":"urlopen(url)",'
            '"proposed":"validate_url(url)","benefit":"Исключает небезопасные схемы"}]}'
        )
        items = parse_improvement_suggestions(response)
        self.assertEqual(items[0]["location"], "main.py.ApiClient.fetch")

    def test_parse_empty_improvement_suggestions(self):
        self.assertEqual(parse_improvement_suggestions('{"suggestions":[]}'), [])

    def test_parse_suggestions_inside_markdown_and_surrounding_text(self):
        fence = chr(96) * 3
        response = (
            "Результат анализа:\n" + fence + "json\n"
            '{"suggestions":[{"title":"Обработка {ошибок}","problem":"Нет журнала",'
            '"current":"except: pass","proposed":"except OSError as exc: log(exc)",'
            '"benefit":"Ошибки видны"}]}\n' + fence + "\nГотово."
        )
        items = parse_improvement_suggestions(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Обработка {ошибок}")

    def test_parse_suggestions_repairs_literal_newlines_and_trailing_commas(self):
        response = (
            '{"suggestions":[{"title":"Логи","problem":"Строка первая\nстрока вторая",'
            '"current":"print(1)","proposed":"logger.info(1)",'
            '"benefit":"Диагностика",},],}'
        )
        items = parse_improvement_suggestions(response)
        self.assertEqual(len(items), 1)
        self.assertIn("строка вторая", items[0]["problem"])

    def test_parse_suggestions_recovers_complete_item_from_truncated_wrapper(self):
        response = (
            '{"suggestions":[{"title":"Проверка","problem":"Нет проверки",'
            '"current":"return value","proposed":"if value is None: return False"}'
        )
        items = parse_improvement_suggestions(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Проверка")

    def test_parse_suggestions_accepts_python_style_literal_safely(self):
        response = (
            "{'suggestions': [{'title': 'Локальная проверка', 'current': 'a', "
            "'proposed': 'b', 'problem': None, 'benefit': True}]}"
        )
        items = parse_improvement_suggestions(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["problem"], "None")
        self.assertEqual(items[0]["benefit"], "True")

    def test_parse_suggestions_repairs_regex_backslashes(self):
        response = r'{"suggestions":[{"title":"Regex","current":"pattern = \d+","proposed":"pattern = \\d+"}]}'
        items = parse_improvement_suggestions(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["current"], r"pattern = \d+")

    def test_apply_single_file_diff(self):
        original = "first\nsecond\nthird\n"
        patch = """--- a/main.py
+++ b/main.py
@@ -1,3 +1,3 @@
 first
-second
+SECOND
 third
"""
        self.assertEqual(apply_unified_diff(original, patch, "main.py"), "first\nSECOND\nthird\n")

    def test_apply_diff_relocates_unique_exact_context_when_hunk_line_is_stale(self):
        original = "#!/usr/bin/env python3\n# module header\nVALUE = 1\n"
        patch = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-VALUE = 1\n+VALUE = 2\n"
        )
        updated = apply_unified_diff(original, patch, "main.py")
        self.assertEqual(updated, "#!/usr/bin/env python3\n# module header\nVALUE = 2\n")

    def test_apply_diff_rejects_placeholder_context_not_in_source(self):
        original = "#!/usr/bin/env python3\nVALUE = 1\n"
        patch = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-# main.py original content\n+# updated file\n"
        )
        with self.assertRaisesRegex(ValueError, "шаблонный или устаревший текст"):
            apply_unified_diff(original, patch, "main.py")

    def test_apply_diff_rejects_ambiguous_context(self):
        original = "def one():\n    return 1\n\ndef two():\n    return 1\n"
        patch = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-    return 1\n+    return 2\n"
        )
        with self.assertRaisesRegex(ValueError, "неоднозначен"):
            apply_unified_diff(original, patch, "main.py")

    def test_apply_diff_preserves_windows_crlf(self):
        original = "first\r\nsecond\r\nthird\r\n"
        patch = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,3 +1,3 @@\n"
            " first\n-second\n+SECOND\n third\n"
        )
        self.assertEqual(
            apply_unified_diff(original, patch, "main.py"),
            "first\r\nSECOND\r\nthird\r\n",
        )

    def test_local_self_improvement_uses_longer_timeout_and_safe_context(self):
        from unittest.mock import patch
        import main

        captured = {}
        def fake_post_json(url, payload, headers=None, timeout=180):
            captured.update(url=url, payload=payload, timeout=timeout)
            return {"message": {"content": "diff"}}

        with patch.object(__import__("chat_interface"), "post_json", side_effect=fake_post_json):
            result = main.ISHApp._call_ollama(
                {
                    "ollama_url": "http://localhost:11434",
                    "ollama_model": "qwen2.5:3b",
                    "task_profile": "self_improvement",
                    "resource_pressure": False,
                    "temperature": 0.15,
                },
                [{"role": "user", "content": "prepare a small diff"}],
            )
        self.assertEqual(result, "diff")
        self.assertEqual(captured["timeout"], 900)
        self.assertEqual(captured["payload"]["options"]["num_ctx"], 4096)
        self.assertEqual(captured["payload"]["options"]["num_batch"], 64)

    def test_local_self_improvement_reduces_context_when_system_is_under_pressure(self):
        from unittest.mock import patch
        import main

        captured = {}
        def fake_post_json(url, payload, headers=None, timeout=180):
            captured.update(payload=payload, timeout=timeout)
            return {"message": {"content": "ok"}}

        with patch.object(__import__("chat_interface"), "post_json", side_effect=fake_post_json):
            main.ISHApp._call_ollama(
                {
                    "ollama_url": "http://localhost:11434",
                    "ollama_model": "qwen2.5:3b",
                    "task_profile": "self_improvement",
                    "resource_pressure": True,
                },
                [{"role": "user", "content": "prepare a diff"}],
            )
        self.assertEqual(captured["timeout"], 900)
        self.assertEqual(captured["payload"]["options"]["num_ctx"], 4096)
        self.assertEqual(captured["payload"]["options"]["num_predict"], 1024)

    def test_reject_other_file(self):
        with self.assertRaises(ValueError):
            apply_unified_diff("a\n", "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-a\n+b\n", "main.py")

    def test_reject_mismatched_context(self):
        patch = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n"
        with self.assertRaises(ValueError):
            apply_unified_diff("different\n", patch, "main.py")




class DiffRegenerationTests(unittest.TestCase):
    def test_missing_hunk_retries_until_a_valid_patch_is_generated(self):
        original = "def answer():\n    return 1\n"
        responses = [
            "Вот описание изменений без diff.",
            "--- a/main.py\n+++ b/main.py\nизменений пока нет",
            "--- a/main.py\n+++ b/main.py\n@@ -1,2 +1,2 @@\n def answer():\n-    return 1\n+    return 2\n",
        ]
        calls = []

        def model_call(messages, attempt):
            calls.append((attempt, list(messages)))
            return responses[attempt]

        patch = generate_validated_unified_diff(
            original,
            "main.py",
            [{"role": "system", "content": "Верни diff."}],
            model_call,
            max_attempts=3,
        )

        self.assertEqual(len(calls), 3)
        self.assertEqual([item[0] for item in calls], [0, 1, 2])
        self.assertIn("не было корректного заголовка блока изменений @@", calls[1][1][-1]["content"])
        self.assertEqual(
            apply_unified_diff(original, patch, "main.py"),
            "def answer():\n    return 2\n",
        )

    def test_missing_hunk_after_all_attempts_returns_clear_error(self):
        calls = []

        def model_call(messages, attempt):
            calls.append(attempt)
            return "Пояснение вместо diff."

        with self.assertRaisesRegex(ValueError, "после 3 попыток"):
            generate_validated_unified_diff(
                "value = 1\n",
                "main.py",
                [{"role": "user", "content": "Измени значение"}],
                model_call,
                max_attempts=3,
            )
        self.assertEqual(calls, [0, 1, 2])

    def test_retry_count_is_bounded_to_three(self):
        calls = []

        def model_call(messages, attempt):
            calls.append(attempt)
            return "Нет блока."

        with self.assertRaises(ValueError):
            generate_validated_unified_diff(
                "value = 1\n",
                "main.py",
                [{"role": "user", "content": "Измени значение"}],
                model_call,
                max_attempts=20,
            )
        self.assertEqual(calls, [0, 1, 2])



class MultiFileDiffTests(unittest.TestCase):
    def setUp(self):
        self.sources = {
            "feature.py": "VALUE = 1\n",
            "tests/test_feature.py": None,
        }
        self.patch = (
            "--- a/feature.py\n+++ b/feature.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"
            "--- /dev/null\n+++ b/tests/test_feature.py\n@@ -0,0 +1,5 @@\n"
            "+import unittest\n+import feature\n+\n"
            "+class FeatureTests(unittest.TestCase):\n"
            "+    def test_value(self): self.assertEqual(feature.VALUE, 2)\n"
        )

    def test_split_and_apply_combined_program_and_new_test_diff(self):
        patches = split_multi_file_unified_diff(self.patch)
        self.assertEqual(set(patches), set(self.sources))
        updated = apply_multi_file_unified_diff(self.sources, self.patch)
        self.assertEqual(updated["feature.py"], "VALUE = 2\n")
        self.assertIn("class FeatureTests", updated["tests/test_feature.py"])

    def test_multi_file_diff_rejects_duplicate_file_headers(self):
        duplicate = (
            self.patch
            + "--- a/feature.py\n+++ b/feature.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 3\n"
        )
        with self.assertRaisesRegex(ValueError, "повторные или пересекающиеся"):
            split_multi_file_unified_diff(duplicate)

    def test_multi_file_diff_rejects_unexpected_or_missing_file(self):
        with self.assertRaisesRegex(ValueError, "не совпадает"):
            apply_multi_file_unified_diff({"feature.py": self.sources["feature.py"]}, self.patch)

    def test_multi_file_generator_retries_invalid_file_set(self):
        answers = [
            "--- a/feature.py\n+++ b/feature.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
            self.patch,
        ]
        calls = []

        def model_call(messages, attempt):
            calls.append(attempt)
            return answers[attempt]

        result = generate_validated_multi_file_unified_diff(
            self.sources,
            [{"role": "system", "content": "Return the code and its tests."}],
            model_call,
            max_attempts=3,
        )
        self.assertEqual(calls, [0, 1])
        self.assertEqual(set(apply_multi_file_unified_diff(self.sources, result)), set(self.sources))

    def test_related_test_path_uses_known_project_test_modules(self):
        self.assertEqual(related_test_path("main.py"), "tests/test_core.py")
        self.assertEqual(related_test_path("improvement_delivery.py"), "tests/test_improvement_delivery.py")
        self.assertEqual(related_test_path("pkg/my_feature.py"), "tests/test_my_feature.py")




class PluginTests(unittest.TestCase):
    def test_skill_create_and_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = PluginManager(Path(temp))
            manager.create_skill("Краткие ответы", "Когда прошу кратко", "Отвечай не более чем в пяти предложениях.")
            prompt = manager.build_skill_prompt()
            self.assertIn("Краткие ответы", prompt)
            self.assertIn("пяти предложениях", prompt)

    def test_disabled_python_plugins_do_not_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = PluginManager(Path(temp), enabled_python=False)
            plugin = manager.plugins_dir / "test_plugin.py"
            plugin.write_text('raise RuntimeError("should not run")\n', encoding="utf-8")
            self.assertIsNone(manager.try_handle_command("/hello"))


class UtilityTests(unittest.TestCase):
    def test_application_release_version_is_431(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from main import APP_VERSION
        self.assertEqual(APP_VERSION, "4.3.1")

    def test_saved_container_overrides_legacy_install_directory(self):
        import main
        with tempfile.TemporaryDirectory() as temp:
            container = Path(temp) / "SelectedContainer"
            app = object.__new__(main.ISHApp)
            app.config = {
                "install_root_dir": str(container),
                "install_dir": str(Path(temp) / "OldInstall"),
            }
            self.assertEqual(
                app._selected_install_dir(),
                (container / "App").resolve(),
            )

    def test_version_tuple(self):
        self.assertGreater(version_tuple("v3.1.0"), version_tuple("3.0.9"))

    def test_unsupported_command_is_handled_safely(self):
        result = handle_voice_command("открой powershell и выполни whoami")
        self.assertTrue(result.handled)
        self.assertFalse(result.success)
        self.assertIn("безопасный список", result.message)

    def test_non_command_is_not_handled(self):
        result = handle_voice_command("Расскажи интересный факт")
        self.assertFalse(result.handled)


class UpdaterTests(unittest.TestCase):
    def test_source_update_installs_to_stable_user_programs_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            staged_dir = Path(temp) / "update_staging"
            staged_dir.mkdir()
            staged = staged_dir / "ISH_update.exe"
            staged.write_bytes(b"fake exe bytes")
            install_dir = Path(temp) / "Programs" / "ISH"
            installed = install_from_source(staged, install_dir)
            self.assertEqual(installed, install_dir / "ISH.exe")
            self.assertEqual(installed.read_bytes(), b"fake exe bytes")
            self.assertFalse((install_dir / "ISH.new.exe").exists())

    def test_windows_updater_waits_then_replaces_and_restarts(self):
        script = _powershell_script()
        self.assertIn("AddSeconds(120)", script)
        self.assertIn("CloseMainWindow()", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("ISH.installing.exe", script)
        self.assertIn("Start-Process -FilePath $TargetPath", script)
        self.assertIn("ISH.previous.exe", script)
        self.assertIn("Выполняется откат", script)
        self.assertIn("ПОДТВЕРЖДЕНО", script)
        self.assertIn("$env:MOYA_UPDATE_RECEIPT", script)
        self.assertIn("Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir -WindowStyle Normal -PassThru -ErrorAction Stop", script)
        self.assertNotIn("-ArgumentList $argList", script)

    def test_updater_script_is_written_with_windows_crlf_and_bom(self):
        with tempfile.TemporaryDirectory() as temp:
            path = write_powershell_updater_script(Path(temp) / "update.ps1")
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"\r\n", raw)
            self.assertEqual(raw.replace(b"\r\n", b"").count(b"\n"), 0)
            self.assertIn("Get-FileHash".encode("utf-8"), raw)

    def test_windows_launcher_builds_detached_command_with_exact_target(self):
        from unittest.mock import patch
        import updater_helper
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staged = root / "staging" / "MoyaIshka.exe"
            staged.parent.mkdir()
            staged.write_bytes(b"test exe bytes")
            target = root / "ISH" / "MoyaIshka.exe"
            log = root / "AppData" / "MoyaIshka" / "update.log"
            with patch.object(updater_helper.shutil, "which", return_value="powershell.exe"), \
                 patch.object(updater_helper.subprocess, "Popen") as popen:
                helper = updater_helper.launch_windows_replacement(
                    staged, target, 1234, log, expected_version="4.1.8",
                    receipt_path=log.with_name("update_confirmation.json"), platform_name="nt",
                )
            self.assertTrue(helper.is_file())
            args = popen.call_args.args[0]
            self.assertEqual(Path(args[0]).name.casefold(), "powershell.exe")
            self.assertIn("-File", args)
            self.assertIn(str(staged.resolve()), args)
            self.assertIn(str(target.resolve()), args)
            self.assertIn("4.1.8", args)
            self.assertEqual(
                popen.call_args.kwargs["creationflags"],
                getattr(updater_helper.subprocess, "CREATE_NO_WINDOW", 0),
            )

    def test_windows_updater_retries_process_start_without_creation_flags(self):
        from unittest.mock import patch, Mock
        import updater_helper
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staged = root / "staging" / "MoyaIshka.exe"
            staged.parent.mkdir()
            staged.write_bytes(b"test exe bytes")
            target = root / "ISH" / "MoyaIshka.exe"
            log = root / "AppData" / "MoyaIshka" / "update.log"
            denied = PermissionError(5, "Access is denied")
            process = Mock()
            with (
                patch.object(updater_helper.shutil, "which", return_value="powershell.exe"),
                patch.object(updater_helper.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True),
                patch.object(updater_helper.subprocess, "Popen", side_effect=[denied, process]) as popen,
            ):
                updater_helper.launch_windows_replacement(
                    staged, target, 1234, log, expected_version="4.1.8",
                    receipt_path=log.with_name("update_confirmation.json"), platform_name="nt",
                )
            self.assertEqual(popen.call_count, 2)
            self.assertEqual(popen.call_args_list[0].kwargs["creationflags"], 0x08000000)
            self.assertEqual(popen.call_args_list[1].kwargs["creationflags"], 0)
            self.assertTrue(any("PowerShell-установщик запущен" in line for line in log.read_text(encoding="utf-8").splitlines()))

    def test_staged_exe_first_launch_uses_detached_transactional_installer(self):
        import inspect
        import main
        source = inspect.getsource(main.migrate_staged_exe_on_first_launch)
        self.assertIn("launch_windows_replacement(", source)
        self.assertIn("expected_version=APP_VERSION", source)
        self.assertIn('"update.log"', source)
        self.assertNotIn("shutil.copy2(running_exe, temporary)", source)

    def test_missing_windows_version_metadata_does_not_block_app_handshake(self):
        script = _powershell_script()
        self.assertIn("нет FileVersion/ProductVersion", script)
        self.assertIn("версию подтвердит само приложение при запуске", script)
        self.assertIn("if ($embeddedVersion -notmatch", script)
        self.assertIn("Новая версия не подтвердила запуск", script)

    def test_updater_launcher_creates_log_before_starting_powershell(self):
        from unittest.mock import patch
        import updater_helper
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staged = root / "staging" / "MoyaIshka.exe"
            staged.parent.mkdir()
            staged.write_bytes(b"test exe bytes")
            log = root / "AppData" / "MoyaIshka" / "update.log"
            target = root / "ISH" / "MoyaIshka.exe"
            with patch.object(updater_helper.shutil, "which", return_value="powershell.exe"), \
                 patch.object(updater_helper.subprocess, "Popen"):
                updater_helper.launch_windows_replacement(
                    staged, target, 1234, log, expected_version="4.1.8", platform_name="nt",
                )
            self.assertTrue(log.is_file())
            content = log.read_text(encoding="utf-8")
            self.assertIn("Запуск установщика обновления 4.1.8", content)
            self.assertIn(str(target.resolve()), content)

    def test_updater_confirmation_requires_version_hash_and_exact_target(self):
        script = _powershell_script()
        self.assertIn("ExpectedVersion", script)
        self.assertIn("ExpectedSha256", script)
        self.assertIn("ReceiptPath", script)
        self.assertIn("Новая версия не подтвердила запуск", script)

    def test_user_install_path_is_named_for_app(self):
        self.assertEqual(user_install_dir().name, "ISH")

    def test_explicit_install_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            selected = Path(temp) / "MyApps" / "Ishka"
            self.assertEqual(resolve_install_dir(configured=selected), selected.resolve())
            self.assertEqual(ensure_install_dir_writable(selected), selected.resolve())
            self.assertTrue((selected / ".").exists())

    def test_old_version_scanner_finds_copies_but_excludes_running_exe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current_dir = root / "Installed"
            old_dir = root / "Downloads" / "MoyaIshka_v4.1.1"
            current_dir.mkdir(parents=True)
            old_dir.mkdir(parents=True)
            current_exe = current_dir / "MoyaIshka.exe"
            old_exe = old_dir / "MoyaIshka.exe"
            current_exe.write_bytes(b"current")
            old_exe.write_bytes(b"old version")
            found = scan_application_copies(
                configured_install_dir=old_dir,
                current_exe=current_exe,
                local_app_data=root / "LocalAppData",
                roaming_app_data=root / "RoamingAppData",
                user_home=root / "User",
            )
            paths = {item["path"] for item in found}
            self.assertIn(str(old_exe.resolve()), paths)
            self.assertNotIn(str(current_exe.resolve()), paths)
            old_record = next(item for item in found if item["path"] == str(old_exe.resolve()))
            self.assertEqual(old_record["version"], "4.1.1")

    def test_old_version_delete_removes_only_selected_app_exe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current_exe = root / "Current" / "MoyaIshka.exe"
            old_exe = root / "Old" / "MoyaIshka.exe"
            current_exe.parent.mkdir()
            old_exe.parent.mkdir()
            current_exe.write_bytes(b"current")
            old_exe.write_bytes(b"old")
            with self.assertRaises(ValueError):
                delete_application_copy(current_exe, current_exe=current_exe)
            delete_application_copy(old_exe, current_exe=current_exe)
            self.assertTrue(current_exe.exists())
            self.assertFalse(old_exe.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

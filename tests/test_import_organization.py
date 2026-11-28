# -*- coding: utf-8 -*-
"""Regression checks for readable, grouped module-level imports."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_MODULES = {path.stem for path in ROOT.glob("*.py")}


def _module_name(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        return node.names[0].name
    return str(node.module or "")


def _import_group(module: str) -> int:
    root = module.split(".", 1)[0]
    if root == "__future__":
        return 0
    if root in sys.stdlib_module_names:
        return 1
    if root in PROJECT_MODULES:
        return 3
    return 2


def _top_level_imports(path: str) -> tuple[str, list[ast.Import | ast.ImportFrom]]:
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path)
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    return source, nodes


class ImportOrganizationTests(unittest.TestCase):
    ORDERED_MODULES = (
        "main.py",
        "cloud_sync.py",
        "github_pr.py",
        "google_drive_sync.py",
        "supabase_backup.py",
        "updater_helper.py",
        "windows_control.py",
        "windows_sandbox.py",
        "voice_manager.py",
        "secure_storage.py",
        "app_runtime.py",
        "backup_interface.py",
        "chat_interface.py",
        "cloud_interface.py",
        "memory_interface.py",
        "plugin_interface.py",
        "research_interface.py",
        "self_improvement_interface.py",
        "settings_interface.py",
        "ui_components.py",
        "update_interface.py",
        "voice_interface.py",
        "app_configuration.py",
        "app_helpers.py",
        "app_startup.py",
        "app_initialization_interface.py",
        "app_lifecycle_interface.py",
        "model_settings_interface.py",
        "ui_pages_interface.py",
        "ui_theme_interface.py",
    )

    def test_module_imports_are_grouped_by_dependency_type_and_sorted(self):
        for path in self.ORDERED_MODULES:
            with self.subTest(path=path):
                _source, nodes = _top_level_imports(path)
                keys = []
                for node in nodes:
                    module = _module_name(node)
                    group = _import_group(module)
                    if path == "main.py" and group == 3:
                        continue  # main.py deliberately groups local imports by feature area
                    kind = 0 if isinstance(node, ast.Import) else 1
                    keys.append((group, kind, module.casefold()))
                    if isinstance(node, ast.Import):
                        self.assertEqual(
                            len(node.names), 1,
                            f"{path}:{node.lineno}: split multiple import names onto separate lines",
                        )
                self.assertEqual(
                    keys,
                    sorted(keys),
                    f"{path}: imports must be grouped as standard library, third-party, then application modules",
                )

    def test_main_application_imports_are_grouped_by_feature_area(self):
        source, nodes = _top_level_imports("main.py")
        headings = (
            "# Core desktop interface, memory and plugin services.",
            "# Backup and cloud storage integrations.",
            "# Self-development, dependency analysis and safe proposal delivery.",
            "# Updates, voice input/output, desktop control and online research.",
            "# ISHApp feature modules — extracted methods keep their API through mixins.",
        )
        offsets = [source.index(item) for item in headings]
        heading_lines = [source[:offset].count(chr(10)) + 1 for offset in offsets]
        self.assertEqual(heading_lines, sorted(heading_lines))

        expected = (
            [
                "avatar_widget", "auto_memory", "context_engine", "conversation_store",
                "intelligent_memory", "plugin_manager", "resource_governor", "secure_storage",
            ],
            [
                "backup_cloud", "backup_manager", "cloud_sync",
                "google_drive_sync", "supabase_backup",
            ],
            [
                "background_developer", "github_pr", "improvement_delivery",
                "improvement_testing", "module_dependency_analyzer", "architecture_knowledge", "self_improvement",
            ],
            [
                "temporary_storage", "updater", "updater_helper", "voice_assistant",
                "voice_manager", "web_research", "windows_control", "windows_sandbox",
            ],
            ["app_configuration","app_helpers","app_initialization_interface","app_lifecycle_interface","app_runtime","app_startup","backup_interface","chat_interface","cloud_interface","memory_interface","model_settings_interface","plugin_interface","research_interface","self_improvement_interface","settings_interface","ui_components","ui_pages_interface","ui_theme_interface","update_interface","voice_interface"],
        )
        local_nodes = [
            node for node in nodes
            if _import_group(_module_name(node)) == 3
        ]
        for index, heading_line in enumerate(heading_lines):
            next_heading_line = (
                heading_lines[index + 1] if index + 1 < len(heading_lines) else len(source.splitlines()) + 1
            )
            actual = [
                _module_name(node).split(".", 1)[0]
                for node in local_nodes
                if heading_line < node.lineno < next_heading_line
            ]
            self.assertEqual(actual, expected[index], headings[index])

    def test_imports_inside_functions_are_reserved_for_lazy_or_platform_specific_dependencies(self):
        expected_local = {
            "main.py": {"improvement_testing", "updater_helper"},
            "app_helpers.py": {"pypdf", "docx"},
            "app_initialization_interface.py": {"tkinter.font"},
            "app_startup.py": {"cffi", "_cffi_backend"},
            "improvement_testing.py": {
                "windows_sandbox", "ctypes", "ctypes.wintypes",
                "importlib.machinery", "unittest",
            },
            "plugin_manager.py": {"windows_control"},
            "resource_governor.py": {"psutil", "ctypes"},
            "voice_assistant.py": {"speech_recognition", "piper", "winsound", "pyttsx3"},
            "windows_control.py": {"ctypes", "ctypes.wintypes"},
            "windows_sandbox.py": {"winreg"},
            "updater_helper.py": set(),
            "app_initialization_interface.py": {"tkinter.font"},
            "plugin_interface.py": {"webbrowser"},
        }
        for path, allowed in expected_local.items():
            with self.subTest(path=path):
                tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
                nested = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in tree.body:
                        names = (
                            [item.name for item in node.names]
                            if isinstance(node, ast.Import)
                            else [node.module or ""]
                        )
                        nested.extend(name for name in names if name)
                self.assertLessEqual(
                    set(nested), allowed,
                    f"{path}: unexpected nested import; document its lazy-loading reason or move it to the module block",
                )

    def test_main_has_no_duplicate_top_level_module_imports(self):
        _source, nodes = _top_level_imports("main.py")
        names = []
        for node in nodes:
            kind = "import" if isinstance(node, ast.Import) else "from"
            imported = tuple(item.name for item in node.names)
            names.append((kind, _module_name(node).casefold(), imported))
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()

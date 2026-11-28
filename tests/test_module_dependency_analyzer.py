import tempfile
import unittest
from pathlib import Path

from module_dependency_analyzer import (
    analyze_module_dependencies,
    build_dependency_context,
    format_dependency_report,
    build_project_architecture_index,
    format_project_architecture_index,
    build_function_call_graph,
    analyze_function_data_flow,
    assess_architecture_change_impact,
    build_architecture_intelligence_context,
)


class ModuleDependencyAnalyzerTests(unittest.TestCase):
    def make_project(self, root: Path) -> None:
        (root / "pkg").mkdir()
        (root / "tests").mkdir()
        (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (root / "pkg" / "core.py").write_text(
            "def calculate(value):\n    return value * 2\n", encoding="utf-8",
        )
        (root / "pkg" / "service.py").write_text(
            "from .core import calculate\n\n"
            "def run(value):\n    return calculate(value)\n",
            encoding="utf-8",
        )
        (root / "ui.py").write_text(
            "from pkg.service import run\n\n"
            "def render(value):\n    return run(value)\n",
            encoding="utf-8",
        )
        (root / "unrelated.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "tests" / "test_service.py").write_text(
            "from pkg.core import calculate\n", encoding="utf-8",
        )
        (root / "tests" / "test_ui.py").write_text(
            "import ui\n", encoding="utf-8",
        )
        (root / "tests" / "test_unrelated.py").write_text(
            "import unrelated\n", encoding="utf-8",
        )

    def test_finds_direct_and_transitive_dependents_and_affected_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            result = analyze_module_dependencies(root, "pkg/core.py")
            direct = [row["path"] for row in result["direct_dependents"]]
            transitive = [row["path"] for row in result["transitive_dependents"]]
            self.assertEqual(direct, ["pkg/service.py"])
            self.assertIn("ui.py", transitive)
            self.assertEqual(
                result["affected_tests"],
                ["tests/test_service.py", "tests/test_ui.py"],
            )
            self.assertNotIn(
                "tests/test_unrelated.py", result["affected_tests"],
            )

    def test_resolves_relative_and_absolute_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            result = analyze_module_dependencies(root, "pkg/core.py")
            self.assertEqual(
                [row["path"] for row in result["direct_dependents"]],
                ["pkg/service.py"],
            )
            self.assertEqual(
                [row["path"] for row in result["transitive_dependents"]],
                ["pkg/service.py", "ui.py"],
            )

    def test_report_and_model_context_name_related_components(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            result = analyze_module_dependencies(root, "pkg/core.py")
            report = format_dependency_report(result)
            context = build_dependency_context(root, result, prompt="change calculation")
            self.assertIn("pkg/service.py", report)
            self.assertIn("ui.py", report)
            self.assertIn("tests/test_ui.py", report)
            self.assertIn("pkg/service.py", context)
            self.assertIn("calculate", context)

    def test_resolves_relative_dynamic_import_from_package_initializer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text(
                "import importlib\nworker = importlib.import_module('.worker', __package__)\n",
                encoding="utf-8",
            )
            (root / "pkg" / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
            analysis = analyze_module_dependencies(root, "pkg/worker.py")
            self.assertEqual(
                [item["path"] for item in analysis["direct_dependents"]],
                ["pkg/__init__.py"],
            )

    def test_reports_unresolved_dynamic_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "loader.py").write_text(
                "import importlib\nname = get_module_name()\n"
                "importlib.import_module(name)\n",
                encoding="utf-8",
            )
            result = analyze_module_dependencies(root, "target.py")
            self.assertTrue(any("динамический импорт" in item for item in result["warnings"]))

    def test_rejects_paths_outside_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze_module_dependencies(root, "../target.py")

    def test_project_architecture_index_lists_modules_symbols_and_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            index = build_project_architecture_index(root)
            report = format_project_architecture_index(index, max_chars=5000)
            self.assertGreaterEqual(index["module_count"], 5)
            self.assertGreaterEqual(index["symbol_count"], 3)
            service = next(item for item in index["modules"] if item["path"] == "pkg/service.py")
            self.assertIn("run", [item["name"] for item in service["symbols"]])
            self.assertIn("calculate", service["calls"])
            self.assertIn("pkg/core.py", report)
            self.assertIn("AST", report)

    def test_reports_parse_errors_without_crashing_the_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "broken.py").write_text("def unfinished(:\n", encoding="utf-8")
            result = analyze_module_dependencies(root, "target.py")
            self.assertTrue(any("broken.py" in item for item in result["warnings"]))


    def test_function_call_graph_resolves_local_and_imported_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            graph = build_function_call_graph(root, "pkg/core.py")
            caller_paths = [item["path"] for item in graph["direct_callers"]]
            self.assertEqual(caller_paths, ["pkg/service.py"])
            service = build_function_call_graph(root, "pkg/service.py")
            self.assertTrue(any(item["name"] == "calculate" for item in service["direct_callees"]))

    def test_function_data_flow_reports_inputs_writes_returns_and_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "worker.py").write_text(
                "def save(path, value):\n"
                "    result = open(path, 'w')\n"
                "    result.write(value)\n"
                "    return result.name\n",
                encoding="utf-8",
            )
            result = analyze_function_data_flow(root, "worker.py")
            function = result["functions"][0]
            self.assertEqual(function["parameters"], ["path", "value"])
            self.assertIn("result", function["writes"])
            self.assertIn("file_system", function["side_effects"])
            self.assertEqual(function["returns"], ["result.name"])

    def test_architecture_impact_and_context_report_uncertainty(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            dependency = analyze_module_dependencies(root, "pkg/core.py")
            graph = build_function_call_graph(root, "pkg/core.py")
            flow = analyze_function_data_flow(root, "pkg/core.py")
            impact = assess_architecture_change_impact(dependency, graph, flow)
            context = build_architecture_intelligence_context(root, "pkg/core.py")
            self.assertIn(impact["risk_level"], {"low", "medium", "high"})
            self.assertIn("ОГРАНИЧЕНИЕ", context)
            self.assertIn("вызывающие функции", context)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from architecture_knowledge import (
    format_recent_architecture_lessons,
    record_architecture_lesson,
    refresh_architecture_knowledge,
)


class ArchitectureKnowledgeTests(unittest.TestCase):
    def make_index(self):
        return {
            "module_count": 1,
            "symbol_count": 1,
            "modules": [{
                "path": "worker.py",
                "module": "worker",
                "imports": ["pathlib"],
                "symbols": [{
                    "name": "run",
                    "kind": "function",
                    "line": 1,
                    "end_line": 2,
                    "signature": "def run():",
                }],
                "calls": ["open"],
            }],
        }

    def test_snapshot_fingerprints_source_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            updates = Path(temp) / "Updates"
            root.mkdir()
            source = root / "worker.py"
            source.write_text("def run():\n    return 1\n", encoding="utf-8")
            first = refresh_architecture_knowledge(updates, root, self.make_index())
            second = refresh_architecture_knowledge(updates, root, self.make_index())
            self.assertFalse(first["cache_unchanged"])
            self.assertTrue(second["cache_unchanged"])
            source.write_text("def run():\n    return 2\n", encoding="utf-8")
            third = refresh_architecture_knowledge(updates, root, self.make_index())
            self.assertEqual(third["changed_files"], ["worker.py"])
            self.assertNotEqual(first["project_fingerprint"], third["project_fingerprint"])

    def test_records_bounded_structured_lessons_without_raw_tracebacks(self):
        with tempfile.TemporaryDirectory() as temp:
            updates = Path(temp) / "Updates"
            record_architecture_lesson(updates, {
                "status": "failed",
                "target": "worker.py",
                "files": ["worker.py", "tests/test_worker.py"],
                "tests_run": 5,
                "failures": 1,
                "errors": 0,
                "review_approved": False,
                "error": "must not be persisted",
            })
            context = format_recent_architecture_lessons(updates)
            self.assertIn("tests_failed", context)
            self.assertIn("worker.py", context)
            self.assertNotIn("must not be persisted", context)

    def test_invalid_target_path_is_not_stored(self):
        with tempfile.TemporaryDirectory() as temp:
            updates = Path(temp) / "Updates"
            record_architecture_lesson(updates, {
                "status": "passed",
                "target": "../secret.py",
                "files": [],
            })
            context = format_recent_architecture_lessons(updates)
            self.assertIn("не указана", context)


if __name__ == "__main__":
    unittest.main()

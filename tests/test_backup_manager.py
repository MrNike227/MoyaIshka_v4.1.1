import errno
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backup_manager import (
    BackupError, copy_verified_backups, create_backup, inspect_backup,
    maybe_create_daily_backup, restore_backup, _move_restore_path,
)


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir()
        (self.root / "config.json").write_text(
            json.dumps({"assistant_name": "Ишка", "memory": ["помнить факт"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_database("исходный диалог")
        (self.root / "research_library.json").write_text(
            json.dumps([{"title": "Знание"}], ensure_ascii=False), encoding="utf-8"
        )
        (self.root / "skills").mkdir()
        (self.root / "skills" / "skill.json").write_text('{"name":"Навык"}', encoding="utf-8")
        (self.root / "plugins").mkdir()
        (self.root / "plugins" / "plugin.py").write_text("PLUGIN_NAME = 'test'\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _write_database(self, message):
        db = sqlite3.connect(self.root / "assistant.db")
        try:
            db.execute("CREATE TABLE IF NOT EXISTS messages (body TEXT NOT NULL)")
            db.execute("DELETE FROM messages")
            db.execute("INSERT INTO messages(body) VALUES(?)", (message,))
            db.commit()
        finally:
            db.close()

    def _read_database(self):
        db = sqlite3.connect(self.root / "assistant.db")
        try:
            return db.execute("SELECT body FROM messages").fetchone()[0]
        finally:
            db.close()

    def test_restore_move_falls_back_when_container_and_data_are_on_different_volumes(self):
        source_root = Path(self.temp.name) / "container_temp"
        target_root = Path(self.temp.name) / "data_volume"
        source_root.mkdir()
        target_root.mkdir()
        source = source_root / "assistant.db"
        destination = target_root / "assistant.db"
        source.write_bytes(b"verified database snapshot")

        cross_device = OSError(errno.EXDEV, "cross-device link")
        with patch("backup_manager.os.replace", side_effect=cross_device):
            _move_restore_path(source, destination)

        self.assertEqual(destination.read_bytes(), b"verified database snapshot")
        self.assertFalse(source.exists())

    def test_backup_contains_memory_history_knowledge_skills_and_plugins(self):
        archive = create_backup(self.root, app_version="4.1.9")
        manifest = inspect_backup(archive)
        self.assertEqual(manifest["app_version"], "4.1.9")
        paths = {item["path"] for item in manifest["files"]}
        self.assertIn("assistant.db", paths)
        self.assertIn("config.json", paths)
        self.assertIn("skills/skill.json", paths)
        self.assertIn("plugins/plugin.py", paths)
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(
                package.read("config.json").decode("utf-8"),
                (self.root / "config.json").read_text(encoding="utf-8"),
            )
            database = Path(self.temp.name) / "snapshot.db"
            database.write_bytes(package.read("assistant.db"))
        db = sqlite3.connect(database)
        try:
            self.assertEqual(db.execute("SELECT body FROM messages").fetchone()[0], "исходный диалог")
        finally:
            db.close()

    def test_restore_replaces_user_data_and_creates_pre_restore_snapshot(self):
        archive = create_backup(self.root, app_version="4.1.9")
        self._write_database("новый диалог")
        backup_dir = str(Path(self.temp.name) / "separate_backups")
        (self.root / "config.json").write_text(
            json.dumps({
                "assistant_name": "Новое имя",
                "memory": [],
                "backup_dir": backup_dir,
                "backup_cloud_enabled": True,
                "backup_retention_count": 14,
                "backup_cloud_retention_count": 30,
                "backup_supabase_enabled": True,
                "backup_supabase_retention_count": 14,
            }),
            encoding="utf-8",
        )
        (self.root / "skills" / "new.json").write_text("{}", encoding="utf-8")
        result = restore_backup(archive, self.root, app_version="4.1.9")
        restored_config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(restored_config["assistant_name"], "Ишка")
        self.assertEqual(restored_config["backup_dir"], backup_dir)
        self.assertTrue(restored_config["backup_cloud_enabled"])
        self.assertEqual(restored_config["backup_retention_count"], 14)
        self.assertEqual(restored_config["backup_cloud_retention_count"], 30)
        self.assertTrue(restored_config["backup_supabase_enabled"])
        self.assertEqual(restored_config["backup_supabase_retention_count"], 14)
        self.assertEqual(restored_config["memory"], ["помнить факт"])
        self.assertEqual(self._read_database(), "исходный диалог")
        self.assertTrue((self.root / "skills" / "skill.json").is_file())
        self.assertFalse((self.root / "skills" / "new.json").exists())
        self.assertTrue(Path(result["safety_backup"]).is_file())

    def test_modified_archive_file_fails_sha256_validation(self):
        archive = create_backup(self.root)
        tampered = Path(self.temp.name) / "tampered.zip"
        with zipfile.ZipFile(archive, "r") as source, zipfile.ZipFile(tampered, "w") as target:
            for name in source.namelist():
                payload = source.read(name)
                if name == "config.json":
                    payload = (b"X" + payload[1:]) if payload else b"X"
                target.writestr(name, payload)
        with self.assertRaisesRegex(BackupError, "SHA-256"):
            inspect_backup(tampered)

    def test_path_traversal_is_rejected_before_restore(self):
        archive = Path(self.temp.name) / "unsafe.zip"
        manifest = {
            "format_version": 1,
            "directories": ["skills", "plugins"],
            "files": [{"path": "../outside.txt", "size": 1, "sha256": "0" * 64}],
        }
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("../outside.txt", "x")
            package.writestr("assistant.db", "x")
            package.writestr("manifest.json", json.dumps(manifest))
        with self.assertRaises(BackupError):
            inspect_backup(archive)
        self.assertFalse((Path(self.temp.name) / "outside.txt").exists())

    def test_legacy_backups_are_copied_and_originals_are_kept(self):
        legacy = Path(self.temp.name) / "legacy"
        destination = Path(self.temp.name) / "new_backups"
        archive = create_backup(self.root, app_version="4.1.9", backup_dir=legacy)
        copied, skipped = copy_verified_backups(legacy, destination)
        self.assertEqual((copied, skipped), (1, 0))
        migrated = destination / archive.name
        self.assertTrue(migrated.is_file())
        self.assertTrue(archive.is_file())
        self.assertEqual(inspect_backup(migrated)["app_version"], "4.1.9")
        copied_again, skipped_again = copy_verified_backups(legacy, destination)
        self.assertEqual((copied_again, skipped_again), (0, 0))

    def test_legacy_migration_skips_corrupt_archives(self):
        legacy = Path(self.temp.name) / "legacy_corrupt"
        destination = Path(self.temp.name) / "new_corrupt"
        legacy.mkdir()
        (legacy / "ISH_backup_corrupt.zip").write_bytes(b"not-a-zip")
        copied, skipped = copy_verified_backups(legacy, destination)
        self.assertEqual((copied, skipped), (0, 1))
        self.assertFalse(any(destination.glob("*.zip")))

    def test_daily_backup_honors_custom_directory(self):
        target = Path(self.temp.name) / "custom_daily"
        first = maybe_create_daily_backup(self.root, app_version="4.1.9", backup_dir=target)
        second = maybe_create_daily_backup(self.root, app_version="4.1.9", backup_dir=target)
        self.assertIsNotNone(first)
        self.assertTrue(os.path.samefile(first.parent, target))
        self.assertIsNone(second)

    def test_custom_backup_directory_is_used(self):
        target = Path(self.temp.name) / "D_drive" / "ISH_Backups"
        archive = create_backup(self.root, app_version="4.1.9", backup_dir=target)
        self.assertTrue(archive.is_file())
        self.assertTrue(os.path.samefile(archive.parent, target))

    def test_daily_backup_is_created_only_once_per_day(self):
        first = maybe_create_daily_backup(self.root, app_version="4.1.9")
        second = maybe_create_daily_backup(self.root, app_version="4.1.9")
        self.assertIsNotNone(first)
        self.assertIsNone(second)

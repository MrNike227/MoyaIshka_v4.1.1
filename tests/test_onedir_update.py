import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from package_onedir import build_package, SHA256_CHUNK_BYTES
from updater import _extract_package, _safe_member_path, validate_app_folder
from updater_helper import (
    delete_application_copy,
    scan_application_copies,
    validate_app_directory,
    _directory_updater_script,
    _powershell_script,
)


def write_fake_app(root: Path, version: str = "4.2.1") -> Path:
    app = root / "ISH"
    internal = app / "_internal"
    internal.mkdir(parents=True)
    content = {
        "ISH.exe": b"fake exe",
        "_internal/python311.dll": b"python dll",
        "_internal/vcruntime140.dll": b"runtime 1",
        "_internal/vcruntime140_1.dll": b"runtime 2",
        "_internal/msvcp140.dll": b"runtime 3",
    }
    entries = []
    for relative, data in content.items():
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append({
            "path": relative, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    exe_hash = next(item["sha256"] for item in entries if item["path"] == "ISH.exe")
    manifest = {
        "schema": 1, "version": version, "entrypoint": "ISH.exe",
        "exe_sha256": exe_hash, "files": entries,
    }
    (app / "build_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return app


class OnedirUpdateTests(unittest.TestCase):
    def test_large_package_download_streams_to_disk_and_checks_size(self):
        from unittest.mock import patch
        from io import BytesIO
        from updater import _download_to, DOWNLOAD_CHUNK_BYTES

        class FakeResponse:
            headers = {"Content-Length": "6"}
            def __init__(self):
                self.stream = BytesIO(b"abcdef")
                self.read_sizes = []
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, size=-1):
                self.read_sizes.append(size)
                return self.stream.read(size)

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "download.zip"
            response = FakeResponse()
            with patch("updater.urllib.request.urlopen", return_value=response):
                digest, size = _download_to("https://example.test/file", path, 10)
            self.assertEqual(response.read_sizes, [DOWNLOAD_CHUNK_BYTES, DOWNLOAD_CHUNK_BYTES])
            self.assertEqual(size, 6)
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertEqual(digest, hashlib.sha256(b"abcdef").hexdigest())

    def test_stream_download_rejects_announced_oversized_content(self):
        from unittest.mock import patch
        from io import BytesIO
        from updater import _download_to

        class FakeResponse:
            headers = {"Content-Length": "100"}
            def __init__(self):
                self.stream = BytesIO(b"small")
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, size=-1):
                return self.stream.read(size)

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "download.zip"
            with patch("updater.urllib.request.urlopen", return_value=FakeResponse()):
                with self.assertRaisesRegex(RuntimeError, "лимит"):
                    _download_to("https://example.test/file", path, 10)
            self.assertFalse(path.exists())

    def test_update_downloads_use_unique_staging_paths(self):
        import hashlib
        from unittest.mock import patch
        from updater import download_verified_update

        payload = b"unique update package"
        digest = hashlib.sha256(payload).hexdigest()
        package_paths = []

        def fake_download(_url, destination, _limit):
            package_paths.append(destination)
            destination.write_bytes(payload)
            return digest, len(payload)

        def fake_extract(archive, destination, version):
            self.assertEqual(archive.read_bytes(), payload)
            self.assertEqual(version, "4.2.1")
            app = destination / "ISH"
            app.mkdir()
            exe = app / "ISH.exe"
            exe.write_bytes(b"staged")
            return exe

        info = {
            "package_url": "https://example.test/ISH.zip",
            "checksum_url": "https://example.test/ISH.zip.sha256",
            "version": "4.2.1",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "update_staging"
            with patch("updater._get", return_value=digest.encode("ascii")):
                with patch("updater._download_to", side_effect=fake_download):
                    with patch("updater._extract_package", side_effect=fake_extract):
                        first = download_verified_update(info, root)
                        second = download_verified_update(info, root)

            self.assertNotEqual(first.parent, second.parent)
            self.assertNotEqual(package_paths[0], package_paths[1])
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            self.assertFalse(package_paths[0].exists())
            self.assertFalse(package_paths[1].exists())

    def test_update_replace_retries_transient_windows_file_lock(self):
        import os
        from unittest.mock import patch
        from updater import _replace_with_retry

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "update.part"
            destination = root / "update.zip"
            source.write_bytes(b"verified")
            real_replace = os.replace
            calls = []

            def flaky_replace(src, dst):
                calls.append((src, dst))
                if len(calls) < 3:
                    error = OSError("sharing violation")
                    error.winerror = 32
                    raise error
                return real_replace(src, dst)

            with patch("updater.os.replace", side_effect=flaky_replace):
                with patch("updater.time.sleep"):
                    _replace_with_retry(source, destination, attempts=4)

            self.assertEqual(len(calls), 3)
            self.assertEqual(destination.read_bytes(), b"verified")
            self.assertFalse(source.exists())

    def test_directory_updater_installs_directly_without_full_intermediate_copy(self):
        script = _directory_updater_script()
        self.assertIn("$stagedHash = VerifyFolder $StagedDir", script)
        self.assertIn("CopyDirectoryContents $TargetDir $BackupDir", script)
        self.assertIn("VerifyBackupCopy $TargetDir $BackupDir", script)
        self.assertIn("ClearDirectoryContents $TargetDir", script)
        self.assertIn("CopyDirectoryContents $StagedDir $TargetDir", script)
        self.assertIn("$ExeHash = VerifyFolder $TargetDir", script)
        self.assertIn("if ($ExeHash -ne $stagedHash)", script)
        self.assertNotIn("$TempDir", script)
        self.assertNotIn("$copiedHash", script)
        self.assertNotIn("Move-Item -LiteralPath $TargetDir -Destination $BackupDir", script)
        self.assertIn("/MT:16", script)
        self.assertNotIn("/MT:8", script)

    def test_successful_single_exe_update_cleans_rollback_copies_after_receipt(self):
        script = _powershell_script()
        receipt_check = script.index(
            "if (-not $confirmed) { throw 'Новая версия не подтвердила запуск за 90 секунд. Выполняется откат.' }"
        )
        cleanup = script.index("Удалена резервная копия после подтверждения обновления")
        self.assertGreater(cleanup, receipt_check)
        self.assertIn("foreach ($obsolete in @($backup, $oldSwap))", script)
        self.assertIn("ПРЕДУПРЕЖДЕНИЕ: не удалось удалить резервную копию", script)

    def test_successful_onedir_update_cleans_backup_and_staging_after_receipt(self):
        script = _directory_updater_script()
        receipt_check = script.index("if (-not $confirmed) { throw 'Новая версия не подтвердила запуск за 90 секунд.' }")
        backup_cleanup = script.index('Log "Резервная папка старой версии удалена: $BackupDir"')
        staging_cleanup = script.index("Remove-Item -LiteralPath $StagedDir -Recurse -Force")
        self.assertGreater(backup_cleanup, receipt_check)
        self.assertGreater(staging_cleanup, receipt_check)
        self.assertIn("Remove-Item -LiteralPath $BackupDir -Recurse -Force -ErrorAction Stop", script)
        self.assertIn("ISH_update_*", script)
        self.assertIn("ПРЕДУПРЕЖДЕНИЕ: не удалось удалить резервную папку", script)

    def test_moyaishka_named_copy_is_found_in_legacy_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            local = root / "local"
            roaming = root / "roaming"
            home.mkdir()
            local.mkdir()
            roaming.mkdir()
            legacy = local / "MoyaIshka"
            internal = legacy / "_internal"
            internal.mkdir(parents=True)
            executable = legacy / "Moyaishka.exe"
            executable.write_bytes(b"old moyaishka")
            (internal / "python311.dll").write_bytes(b"runtime")

            results = scan_application_copies(
                current_exe=home / "active" / "ISH.exe",
                local_app_data=local,
                roaming_app_data=roaming,
                user_home=home,
            )
            found_paths = {Path(item["path"]) for item in results}
            self.assertIn(executable.resolve(), found_paths)

    def test_delete_moyaishka_onedir_copy_removes_its_program_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root / "MoyaIshka"
            internal = app / "_internal"
            internal.mkdir(parents=True)
            executable = app / "Moyaishka.exe"
            executable.write_bytes(b"old app")
            (internal / "python311.dll").write_bytes(b"runtime")

            delete_application_copy(executable, current_exe=root / "current" / "ISH.exe")

            self.assertFalse(app.exists())

    def test_delete_legacy_moyaishka_exe_preserves_unrelated_folder_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "MoyaIshka"
            folder.mkdir()
            executable = folder / "Moyaishka.exe"
            executable.write_bytes(b"legacy exe")
            notes = folder / "notes.txt"
            notes.write_text("user file", encoding="utf-8")

            delete_application_copy(executable)

            self.assertFalse(executable.exists())
            self.assertTrue(notes.is_file())
            self.assertTrue(folder.is_dir())

    def test_deleting_copy_in_active_onedir_folder_never_removes_active_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "ISH"
            internal = app / "_internal"
            internal.mkdir(parents=True)
            active = app / "ISH.exe"
            active.write_bytes(b"active")
            duplicate = app / "MoyaIshka.exe"
            duplicate.write_bytes(b"duplicate")
            (app / "build_manifest.json").write_text(
                json.dumps({"entrypoint": "MoyaIshka.exe", "files": []}),
                encoding="utf-8",
            )

            delete_application_copy(duplicate, current_exe=active)

            self.assertTrue(active.is_file())
            self.assertTrue(app.is_dir())
            self.assertFalse(duplicate.exists())

    def test_download_extract_and_hash_buffers_are_fifty_megabytes(self):
        from updater import (
            DOWNLOAD_CHUNK_BYTES, FILE_HASH_CHUNK_BYTES,
            EXTRACT_CHUNK_BYTES, MAX_PACKAGE_BYTES,
        )
        from updater_helper import FILE_HASH_CHUNK_BYTES as INSTALL_HASH_CHUNK_BYTES

        expected = 50 * 1024 * 1024
        self.assertEqual(MAX_PACKAGE_BYTES, 2 * 1024 * 1024 * 1024)
        self.assertEqual(DOWNLOAD_CHUNK_BYTES, expected)
        self.assertEqual(FILE_HASH_CHUNK_BYTES, expected)
        self.assertEqual(EXTRACT_CHUNK_BYTES, expected)
        self.assertEqual(INSTALL_HASH_CHUNK_BYTES, expected)
        self.assertEqual(SHA256_CHUNK_BYTES, expected)

    def test_archive_path_traversal_is_rejected(self):
        for path in ("../evil.txt", "ISH/../../evil.txt", "/ISH/file", "C:/evil.txt"):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                _safe_member_path(path)

    def test_legacy_archive_root_remains_accepted_for_upgrade(self):
        self.assertEqual(_safe_member_path("MoyaIshka/MoyaIshka.exe"), ("MoyaIshka", "MoyaIshka.exe"))

    def test_archive_root_must_be_ish(self):
        with self.assertRaisesRegex(RuntimeError, "корневую папку"):
            _safe_member_path("OtherApp/ISH.exe")

    def test_folder_manifest_is_checked_file_by_file(self):
        with tempfile.TemporaryDirectory() as temp:
            app = write_fake_app(Path(temp))
            self.assertEqual(validate_app_folder(app, "4.2.1")["version"], "4.2.1")
            self.assertEqual(validate_app_directory(app, "4.2.1")["version"], "4.2.1")

    def test_unmanifested_runtime_dll_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            app = write_fake_app(Path(temp))
            (app / "_internal" / "unexpected.dll").write_bytes(b"unexpected")
            with self.assertRaisesRegex(RuntimeError, "лишние"):
                validate_app_folder(app, "4.2.1")
            with self.assertRaisesRegex(RuntimeError, "лишние"):
                validate_app_directory(app, "4.2.1")

    def test_tampered_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            app = write_fake_app(Path(temp))
            (app / "_internal/python311.dll").write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "Размер файла"):
                validate_app_folder(app, "4.2.1")

    def test_wrong_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            app = write_fake_app(Path(temp), "4.1.8.3")
            with self.assertRaisesRegex(RuntimeError, "Версия"):
                validate_app_folder(app, "4.2.1")

    def test_built_zip_extracts_to_staging_folder_and_validates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = write_fake_app(root)
            output = root / "ISH.zip"
            build_package(source, output, "4.2.1")
            staged = _extract_package(output, root / "update_staging", "4.2.1")
            self.assertTrue(staged.is_file())
            self.assertTrue((staged.parent / "_internal/python311.dll").is_file())
            self.assertEqual(validate_app_folder(staged.parent, "4.2.1")["version"], "4.2.1")

    def test_duplicate_archive_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("ISH/file.txt", "one")
                bundle.writestr("ISH/file.txt", "two")
            with self.assertRaisesRegex(RuntimeError, "повторяется путь"):
                _extract_package(archive, root / "stage", "4.2.1")


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from temporary_storage import (
    configure_temporary_storage,
    get_temp_directory,
    resolve_container_root,
)


class TemporaryStorageTests(unittest.TestCase):
    def setUp(self):
        self._environment = {
            key: os.environ.get(key)
            for key in ("TEMP", "TMP", "TMPDIR", "MOYA_TEMP_ROOT", "MOYA_CONTAINER_ROOT")
        }
        self._tempfile_tempdir = tempfile.tempdir
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for key in self._environment:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tempfile.tempdir = self._tempfile_tempdir
        self.temp.cleanup()

    def test_explicit_container_root_receives_all_runtime_temp_variables(self):
        container = self.root / "SelectedContainer"
        temp_root = configure_temporary_storage({"install_root_dir": str(container)})

        self.assertEqual(temp_root, (container / "Temp").resolve())
        self.assertTrue(temp_root.is_dir())
        self.assertEqual(Path(os.environ["TEMP"]), temp_root)
        self.assertEqual(Path(os.environ["TMP"]), temp_root)
        self.assertEqual(Path(os.environ["TMPDIR"]), temp_root)
        self.assertEqual(Path(os.environ["MOYA_TEMP_ROOT"]), temp_root)
        self.assertEqual(Path(tempfile.gettempdir()), temp_root)

    def test_app_folder_setting_resolves_to_container_parent(self):
        container = self.root / "ISH_Container"
        app = container / "App"
        resolved = resolve_container_root({"install_dir": str(app)})
        self.assertEqual(resolved, container.resolve())

    def test_legacy_install_folder_resolves_to_new_default_container(self):
        programs = self.root / "Programs"
        legacy_install = programs / "ISH"
        resolved = resolve_container_root({"install_dir": str(legacy_install)})
        self.assertEqual(resolved, (programs / "ISH_Container").resolve())

    def test_container_root_saved_in_install_dir_is_not_nested(self):
        container = self.root / "ISH_Container"
        resolved = resolve_container_root({"install_dir": str(container)})
        self.assertEqual(resolved, container.resolve())

    def test_running_executable_resolves_app_container_without_config(self):
        container = self.root / "ISH_Container"
        executable = container / "App" / "ISH.exe"
        resolved = resolve_container_root({}, running_path=executable)
        self.assertEqual(resolved, container.resolve())

    def test_staged_executable_resolves_container_from_update_staging(self):
        container = self.root / "ISH_Container"
        executable = container / "Temp" / "update_staging" / "ISH.exe"
        resolved = resolve_container_root({}, running_path=executable)
        self.assertEqual(resolved, container.resolve())

    def test_changing_container_reconfigures_python_tempfile_cache(self):
        first = self.root / "First"
        second = self.root / "Second"
        configure_temporary_storage({"install_root_dir": str(first)})
        configured = configure_temporary_storage({"install_root_dir": str(second)})

        self.assertEqual(configured, (second / "Temp").resolve())
        self.assertEqual(Path(tempfile.gettempdir()), configured)
        self.assertEqual(Path(os.environ["TEMP"]), configured)

    def test_get_temp_directory_honors_new_config_even_when_environment_is_old(self):
        first = self.root / "OldContainer"
        second = self.root / "NewContainer"
        configure_temporary_storage({"install_root_dir": str(first)})

        new_directory = get_temp_directory(
            "download",
            config={"install_root_dir": str(second)},
        )

        self.assertEqual(new_directory, (second / "Temp" / "download").resolve())
        self.assertEqual(Path(os.environ["TEMP"]), (second / "Temp").resolve())

    def test_category_directory_stays_below_container_temp(self):
        container = self.root / "Container"
        configure_temporary_storage({"install_root_dir": str(container)})
        work = get_temp_directory("self_development", config={"install_root_dir": str(container)})

        self.assertEqual(work.parent, (container / "Temp").resolve())
        self.assertTrue(work.is_dir())
        with self.assertRaises(ValueError):
            get_temp_directory("../outside")
        with self.assertRaises(ValueError):
            get_temp_directory(r"..\outside")

    def test_reparse_point_temp_root_is_rejected(self):
        container = self.root / "JunctionContainer"
        with patch("temporary_storage._is_reparse_point", return_value=True):
            with self.assertRaisesRegex(OSError, "ссылкой или junction"):
                configure_temporary_storage({"install_root_dir": str(container)})

    def test_unavailable_container_fails_instead_of_using_system_temp(self):
        blocked_file = self.root / "not_a_directory"
        blocked_file.write_text("block", encoding="utf-8")
        with self.assertRaisesRegex(OSError, "Системная папка TEMP не используется"):
            configure_temporary_storage({"install_root_dir": str(blocked_file / "Container")})


if __name__ == "__main__":
    unittest.main()

import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseBuildTests(unittest.TestCase):
    def test_build_uses_onedir_and_manifested_zip(self):
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        self.assertIn("--onedir --contents-directory _internal", build)
        self.assertNotIn("--onefile", build)
        self.assertIn("dist\\ISH\\ISH.exe", build)
        self.assertIn("package_onedir.py", build)
        self.assertIn('--add-data "backup_manager.py;source_project"', build)
        self.assertIn('--add-data "backup_cloud.py;source_project"', build)
        self.assertIn('--add-data "intelligent_memory.py;source_project"', build)
        self.assertIn('--add-data "improvement_delivery.py;source_project"', build)
        self.assertIn('--add-data "improvement_testing.py;source_project"', build)
        self.assertIn('--add-data "module_dependency_analyzer.py;source_project"', build)
        self.assertIn('--add-data "github_pr.py;source_project"', build)
        self.assertIn('--add-data "temporary_storage.py;source_project"', build)
        self.assertIn('--add-data "conversation_store.py;source_project"', build)
        self.assertIn('--add-data "secure_storage.py;source_project"', build)
        self.assertIn('--add-data "app_configuration.py;source_project"', build)
        self.assertIn('--add-data "app_helpers.py;source_project"', build)
        self.assertIn('--add-data "app_startup.py;source_project"', build)
        self.assertIn('--add-data "app_initialization_interface.py;source_project"', build)
        self.assertIn('--add-data "app_lifecycle_interface.py;source_project"', build)
        self.assertIn('--add-data "model_settings_interface.py;source_project"', build)
        self.assertIn('--add-data "ui_pages_interface.py;source_project"', build)
        self.assertIn('--add-data "ui_theme_interface.py;source_project"', build)
        self.assertIn('--add-data "app_runtime.py;source_project"', build)
        self.assertIn('--add-data "backup_interface.py;source_project"', build)
        self.assertIn('--add-data "chat_interface.py;source_project"', build)
        self.assertIn('--add-data "cloud_interface.py;source_project"', build)
        self.assertIn('--add-data "memory_interface.py;source_project"', build)
        self.assertIn('--add-data "plugin_interface.py;source_project"', build)
        self.assertIn('--add-data "research_interface.py;source_project"', build)
        self.assertIn('--add-data "self_improvement_interface.py;source_project"', build)
        self.assertIn('--add-data "settings_interface.py;source_project"', build)
        self.assertIn('--add-data "ui_components.py;source_project"', build)
        self.assertIn('--add-data "update_interface.py;source_project"', build)
        self.assertIn('--add-data "voice_interface.py;source_project"', build)
        self.assertIn('--add-data "PLAN_4.2.6_RU.md;source_project"', build)
        self.assertIn('--add-data "PLAN_4.2.7_RU.md;source_project"', build)
        self.assertIn('--add-data "PLAN_4.2.8_RU.md;source_project"', build)
        self.assertIn('--add-data "PLAN_4.3.1_RU.md;source_project"', build)
        self.assertIn("dist\\ISH.zip", build)
        self.assertIn("api-ms-win-crt-", build)
        self.assertIn("ucrtbase.dll", build)

    def test_module_dependency_analyzer_is_in_packaged_source_workspace(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        workspace_source = (ROOT / "app_helpers.py").read_text(encoding="utf-8")
        self.assertIn("from module_dependency_analyzer import (", source)
        self.assertIn("from conversation_store import Store, load_json, now_iso, pretty_time", source)
        self.assertIn("from secure_storage import DATA_BLOB, dpapi_transform, protect_api_key, unprotect_api_key, unprotect_github_pr_token", source)
        self.assertNotIn("class DATA_BLOB(", source)
        self.assertNotIn("def dpapi_transform(", source)
        self.assertIn("secure_storage.py", workspace_source)
        self.assertIn("tests/test_secure_storage.py", workspace_source)
        self.assertIn('"app_configuration.py"', workspace_source)
        self.assertIn('"app_helpers.py"', workspace_source)
        self.assertIn('"app_startup.py"', workspace_source)
        self.assertIn('"app_initialization_interface.py"', workspace_source)
        self.assertIn('"app_lifecycle_interface.py"', workspace_source)
        self.assertIn('"model_settings_interface.py"', workspace_source)
        self.assertIn('"ui_pages_interface.py"', workspace_source)
        self.assertIn('"ui_theme_interface.py"', workspace_source)
        self.assertIn('"app_runtime.py"', workspace_source)
        self.assertIn('"backup_interface.py"', workspace_source)
        self.assertIn('"chat_interface.py"', workspace_source)
        self.assertIn('"cloud_interface.py"', workspace_source)
        self.assertIn('"memory_interface.py"', workspace_source)
        self.assertIn('"plugin_interface.py"', workspace_source)
        self.assertIn('"research_interface.py"', workspace_source)
        self.assertIn('"self_improvement_interface.py"', workspace_source)
        self.assertIn('"settings_interface.py"', workspace_source)
        self.assertIn('"ui_components.py"', workspace_source)
        self.assertIn('"update_interface.py"', workspace_source)
        self.assertIn('"voice_interface.py"', workspace_source)
        self.assertIn("class ISHApp(", source)
        self.assertNotIn("class Store:", source)
        dependency_imports = source.split("from module_dependency_analyzer import (", 1)[1].split(")", 1)[0]
        self.assertIn("analyze_module_dependencies", dependency_imports)
        self.assertIn('"module_dependency_analyzer.py"', workspace_source)
        self.assertIn('"tests/test_module_dependency_analyzer.py"', workspace_source)
        self.assertIn('"PLAN_4.2.7_RU.md"', workspace_source)
        self.assertIn('"PLAN_4.2.8_RU.md"', workspace_source)
        self.assertIn('"PLAN_4.3.1_RU.md"', workspace_source)
        self.assertIn('"tests/test_multi_file_diff_recovery.py"', workspace_source)
        self.assertIn('"temporary_storage.py"', workspace_source)
        self.assertIn('"conversation_store.py"', workspace_source)
        self.assertIn('"tests/test_temporary_storage.py"', workspace_source)
        self.assertIn('"Workspaces"', workspace_source)

    def test_runtime_temporary_workspaces_use_container_storage(self):
        checks = {
            "update_interface.py": ('get_temp_directory("update_staging"',),
            "backup_interface.py": ('get_temp_directory("cloud_restore"',),
            "updater_helper.py": ('get_temp_directory("installers")',),
            "improvement_testing.py": ('get_temp_directory("self_development")',),
            "windows_sandbox.py": ('get_temp_directory("sandbox_setup")',),
            "voice_assistant.py": ('get_temp_directory("voice")',),
            "backup_manager.py": ('get_temp_directory("backups")', 'get_temp_directory("backup_restore")'),
        }
        for filename, required in checks.items():
            source = (ROOT / filename).read_text(encoding="utf-8")
            for marker in required:
                with self.subTest(filename=filename, marker=marker):
                    self.assertIn(marker, source)

    def test_pyinstaller_bootloader_version_is_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pyinstaller==6.22.3", requirements)

    def test_default_backup_folder_is_outside_application_directory(self):
        from main import default_backup_directory
        backup_dir = default_backup_directory()
        self.assertEqual(backup_dir.name, "ISH_Backups")
        self.assertNotEqual(backup_dir.parent.name, "ISH_Backups")

    def test_application_identity_is_ish(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        config = (ROOT / "app_configuration.py").read_text(encoding="utf-8")
        self.assertIn('APP_NAME = "ISH"', config)
        self.assertIn("class ISHApp(", source)
        self.assertNotIn("class MoyaIshkaApp:", source)
        self.assertIn('"assistant_name": "ISH"', config)

    def test_legacy_user_data_is_copied_to_ish_without_deleting_source(self):
        import os
        from unittest.mock import patch
        from main import user_data_dir
        with tempfile.TemporaryDirectory() as temp:
            appdata = Path(temp)
            legacy = appdata / "MoyaIshka"
            legacy.mkdir()
            (legacy / "config.json").write_text('{"assistant_name":"old"}', encoding="utf-8")
            with patch.dict(os.environ, {"APPDATA": str(appdata)}):
                target = user_data_dir()
            self.assertEqual(target, appdata / "ISH")
            self.assertEqual((target / "config.json").read_text(encoding="utf-8"), '{"assistant_name":"old"}')
            self.assertTrue((legacy / "config.json").is_file())

    def test_application_version_is_431(self):
        source = (ROOT / "app_configuration.py").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "4.3.1"', source)

    def test_legacy_update_repository_is_migrated(self):
        from main import migrate_update_repository
        config = {"update_repo": "MrNike227/MoyaIshka_v4.1.1"}
        self.assertTrue(migrate_update_repository(config))
        self.assertEqual(config["update_repo"], "MrNike227/MoyaIshka")

    def test_custom_update_repository_is_preserved(self):
        from main import migrate_update_repository
        config = {"update_repo": "someone/custom-fork"}
        self.assertFalse(migrate_update_repository(config))
        self.assertEqual(config["update_repo"], "someone/custom-fork")

    def test_empty_update_repository_gets_current_default(self):
        from main import migrate_update_repository
        config = {"update_repo": " "}
        self.assertTrue(migrate_update_repository(config))
        self.assertEqual(config["update_repo"], "MrNike227/MoyaIshka")

    def test_python_vc_runtime_is_bundled_without_redundant_windows_ucrt(self):
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        helper = (ROOT / "prepare_python_runtime.py").read_text(encoding="utf-8")
        self.assertIn("%PY% prepare_python_runtime.py", build)
        self.assertIn('--add-binary "build_runtime\\python_runtime;."', build)
        self.assertIn("vcruntime140.dll", helper)
        self.assertIn("vcruntime140_1.dll", helper)
        self.assertIn("discover_visual_c_runtime_roots", helper)
        self.assertIn("Microsoft Visual Studio", helper)
        self.assertIn('"vcruntime140.dll"', helper)
        self.assertIn('"vcruntime140_1.dll"', helper)
        self.assertIn('"msvcp140.dll"', helper)
        self.assertNotIn('"ucrtbase.dll"', helper)
        self.assertNotIn('"api-ms-win-crt-*.dll"', helper)
        audit = (ROOT / "verify_pe_dependencies.py").read_text(encoding="utf-8")
        self.assertIn("runtime.rglob", audit)
        self.assertIn("DIRECTORY_ENTRY_DELAY_IMPORT", audit)
        self.assertIn("LoadLibraryExW", audit)
        self.assertIn("LOAD_LIBRARY_SEARCH_SYSTEM32", audit)

    def test_runtime_dll_collector_copies_only_vc_runtime(self):
        from prepare_python_runtime import collect_runtime_dlls
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "python"
            destination = root / "bundle"
            source.mkdir()
            def write_pe(path, machine=0x8664):
                data = bytearray(0x86)
                data[:2] = b"MZ"
                data[0x3C:0x40] = (0x80).to_bytes(4, "little")
                data[0x80:0x84] = b"PE\0\0"
                data[0x84:0x86] = machine.to_bytes(2, "little")
                path.write_bytes(data)

            write_pe(source / "vcruntime140.dll")
            write_pe(source / "vcruntime140_1.dll")
            write_pe(source / "msvcp140.dll")
            copied = collect_runtime_dlls([source], destination)
            self.assertEqual(
                {item.name for item in copied},
                {"vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"},
            )
            self.assertFalse((destination / "ucrtbase.dll").exists())
            self.assertFalse((destination / "api-ms-win-crt-runtime-l1-1-0.dll").exists())
            self.assertEqual((destination / "vcruntime140.dll").read_bytes()[:2], b"MZ")

    def test_runtime_dll_collector_rejects_32_bit_runtime_dll(self):
        from prepare_python_runtime import collect_runtime_dlls
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "python"
            source.mkdir()

            def write_pe(path, machine=0x8664):
                data = bytearray(0x86)
                data[:2] = b"MZ"
                data[0x3C:0x40] = (0x80).to_bytes(4, "little")
                data[0x80:0x84] = b"PE\0\0"
                data[0x84:0x86] = machine.to_bytes(2, "little")
                path.write_bytes(data)

            write_pe(source / "vcruntime140.dll", 0x14C)
            write_pe(source / "vcruntime140_1.dll")
            write_pe(source / "msvcp140.dll")
            with self.assertRaisesRegex(RuntimeError, "требуется x64"):
                collect_runtime_dlls([source], root / "bundle")

    def test_runtime_dll_collector_fails_when_core_runtime_is_missing(self):
        from prepare_python_runtime import collect_runtime_dlls
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "python"
            source.mkdir()
            with self.assertRaisesRegex(RuntimeError, "vcruntime140.dll"):
                collect_runtime_dlls([source], root / "bundle")


    def test_runtime_dll_collector_finds_missing_python_dlls_in_visual_studio_redist(self):
        import os
        from unittest.mock import patch
        from prepare_python_runtime import collect_runtime_dlls, discover_visual_c_runtime_roots

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            python = root / "python311"
            python.mkdir()
            redist = (
                root / "Microsoft Visual Studio" / "2022" / "BuildTools" / "VC" / "Redist"
                / "MSVC" / "14.42.34433" / "x64" / "Microsoft.VC143.CRT"
            )
            redist.mkdir(parents=True)

            def write_pe(path):
                data = bytearray(0x86)
                data[:2] = b"MZ"
                data[0x3C:0x40] = (0x80).to_bytes(4, "little")
                data[0x80:0x84] = b"PE\0\0"
                data[0x84:0x86] = (0x8664).to_bytes(2, "little")
                path.write_bytes(data)

            for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
                write_pe(redist / name)

            environment = {
                "ProgramFiles": str(root),
                "ProgramFiles(x86)": str(root),
                "VCToolsRedistDir": "",
                "VSINSTALLDIR": "",
            }
            with patch.dict(os.environ, environment):
                roots = discover_visual_c_runtime_roots()
                self.assertIn(redist.resolve(), roots)
                copied = collect_runtime_dlls([python, *roots], root / "bundle")

            self.assertEqual(
                {path.name for path in copied},
                {"vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"},
            )
            for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
                self.assertEqual((root / "bundle" / name).read_bytes()[:2], b"MZ")

    def test_cryptography_is_explicitly_collected(self):
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        self.assertIn("--additional-hooks-dir hooks", build)
        self.assertIn("--collect-all cryptography", build)
        self.assertIn("--collect-submodules cryptography", build)
        self.assertIn("--collect-binaries cryptography", build)
        self.assertIn("--hidden-import=cryptography", build)
        self.assertIn("--hidden-import=cryptography.hazmat.bindings._rust", build)
        self.assertIn("--copy-metadata cryptography", build)
        self.assertIn("--self-test-imports", build)

    def test_custom_cryptography_hook_collects_package(self):
        hook = ROOT / "hooks" / "hook-cryptography.py"
        self.assertTrue(hook.is_file())
        source = hook.read_text(encoding="utf-8")
        self.assertIn('collect_all("cryptography")', source)
        self.assertIn('collect_all("cffi")', source)
        self.assertIn('"_cffi_backend"', source)
        self.assertIn('cryptography.hazmat.bindings._rust', source)

    def test_cffi_backend_is_declared_and_collected(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        self.assertIn("cffi>=2.0.0", requirements)
        self.assertIn("--collect-all cffi", build)
        self.assertIn("--hidden-import=_cffi_backend", build)

    def test_frozen_smoke_test_requires_app_local_runtime_dlls(self):
        source = (ROOT / "app_startup.py").read_text(encoding="utf-8")
        self.assertIn('getattr(sys, "frozen", False)', source)
        self.assertIn('"vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"', source)
        self.assertNotIn("ucrtbase.dll", source)
        self.assertIn('"_MEIPASS"', source)

    def test_runtime_smoke_test_performs_aes_gcm_roundtrip(self):
        source = (ROOT / "app_startup.py").read_text(encoding="utf-8")
        entrypoint = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('"--self-test-imports"', entrypoint)
        self.assertIn("_CryptoAESGCM", source)
        self.assertIn("_CryptoScrypt", source)
        self.assertIn("cipher.decrypt", source)
        self.assertIn('smoke_aad = f"{APP_VERSION}-smoke".encode("ascii")', source)
        self.assertEqual(source.count("smoke_aad"), 3)
        self.assertIn("import _cffi_backend", source)

    def test_github_actions_use_node24_compatible_action_majors(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7.1.0", workflow)
        self.assertNotIn("softprops/action-gh-release@v2", workflow)
        self.assertIn("Verify app-local VC runtime DLLs are present", workflow)
        self.assertIn("dist/ISH/_internal", workflow)
        self.assertIn("Verify onedir EXE starts without Python on PATH", workflow)
        self.assertIn("[System.Diagnostics.Process]::Start($startInfo)", workflow)
        self.assertIn("$process.ExitCode", workflow)
        self.assertIn("if ($process.ExitCode -ne 0)", workflow)
        self.assertIn("Audit python311.dll PE dependency tree on Windows", workflow)
        self.assertIn("runs-on: windows-2022", workflow)
        self.assertNotIn("build_patched_pyinstaller.py", workflow)

    def test_windows_and_voice_page_has_mousewheel_scroll_container(self):
        source = (ROOT / "ui_pages_interface.py").read_text(encoding="utf-8")
        page_start = source.index("    def _build_windows_page(self) -> None:")
        page_end = source.index("    def _build_workshop_page(self) -> None:", page_start)
        windows_page = source[page_start:page_end]
        self.assertIn("scroll_canvas = tk.Canvas(page", windows_page)
        self.assertIn('ttk.Scrollbar(page, orient="vertical", command=scroll_canvas.yview)', windows_page)
        self.assertIn("body = ttk.Frame(scroll_canvas)", windows_page)
        self.assertIn("scroll_canvas.create_window", windows_page)
        self.assertIn('"<Configure>"', windows_page)
        self.assertIn("self.windows_page_canvas = scroll_canvas", windows_page)
        chat_source = (ROOT / "chat_interface.py").read_text(encoding="utf-8")
        self.assertIn("if isinstance(ancestor, tk.Canvas):", chat_source)
        self.assertIn("ancestor.yview_scroll(steps, \"units\")", chat_source)

    def test_native_dependency_audit_is_required_before_release(self):
        audit = (ROOT / "verify_pe_dependencies.py").read_text(encoding="utf-8")
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("runtime.rglob", audit)
        self.assertIn("DIRECTORY_ENTRY_DELAY_IMPORT", audit)
        self.assertIn("LoadLibraryExW", audit)
        self.assertIn("LOAD_WITH_ALTERED_SEARCH_PATH", audit)
        self.assertIn("%PY% verify_pe_dependencies.py", build)
        self.assertIn("Audit python311.dll PE dependency tree on Windows", workflow)
        self.assertIn("python verify_pe_dependencies.py dist/ISH", workflow)

    def test_context_engine_is_bundled_and_used(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        workspace_source = (ROOT / "app_helpers.py").read_text(encoding="utf-8")
        self.assertIn("select_memory_records", source)
        self.assertIn("MEMORY_CONTEXT_START", source)
        self.assertIn("trim_conversation_context", source)
        self.assertIn("context_engine.py", workspace_source)
        self.assertTrue((ROOT / "tests" / "test_context_engine.py").is_file())

    def test_workflow_parses_folder_updater_with_windows_powershell(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("Validate PowerShell folder updater syntax", workflow)
        self.assertIn("[System.Management.Automation.Language.Parser]::ParseFile", workflow)

    def test_directory_updater_sets_base_before_relative_path_enumeration(self):
        helper = (ROOT / "updater_helper.py").read_text(encoding="utf-8")
        script_start = helper.index("def _directory_updater_script")
        script_end = helper.index("def launch_windows_directory_replacement", script_start)
        script = helper[script_start:script_end]
        self.assertLess(
            script.index("$base = [IO.Path]::GetFullPath($Folder)"),
            script.index("$treeItems = @(Get-ChildItem -LiteralPath $Folder -Force -Recurse"),
        )

    def test_migration_persists_app_target_only_after_user_confirmation(self):
        source = (ROOT / "update_interface.py").read_text(encoding="utf-8")
        start = source.index("    def install_current_build_to_selected_folder(self) -> None:")
        end = source.index("    def search_old_versions(self) -> None:", start)
        method = source[start:end]
        frozen_start = method.index("            current_dir = Path(sys.executable).resolve().parent")
        confirmation = method.index('if not messagebox.askyesno(', frozen_start)
        staging = method.index("shutil.copytree(current_dir, staged_dir)", confirmation)
        staged_validation = method.index("validate_app_directory(staged_dir, APP_VERSION)", staging)
        persist_target = method.index('self.config["install_dir"] = str(destination)', staged_validation)
        launch = method.index("launch_windows_directory_replacement(", persist_target)
        self.assertLess(confirmation, staging)
        self.assertLess(staging, staged_validation)
        self.assertLess(staged_validation, persist_target)
        self.assertLess(persist_target, launch)
        self.assertIn("layout['updates']", method)
        self.assertIn("target_dir=destination", method)

    def test_update_download_dialog_selects_container_root_and_targets_app(self):
        source = (ROOT / "chat_interface.py").read_text(encoding="utf-8")
        start = source.index('                elif event == "update_downloaded":')
        end = source.index('                elif event == "old_versions_scan_complete":', start)
        handler = source[start:end]
        self.assertIn("корневую папку контейнера", handler)
        self.assertIn("layout = ensure_install_layout(container_root)", handler)
        self.assertIn('self.config["updates_dir"] = str(layout["updates"])', handler)
        self.assertIn("destination_dir = ensure_install_dir_writable(layout[\"app\"])", handler)
        self.assertIn("self._apply_staged_update(destination_dir)", handler)
        self.assertIn('target = destination_dir / "ISH.exe"', handler)

    def test_container_update_target_uses_app_and_keeps_updates_sibling(self):
        from improvement_delivery import resolve_install_layout
        with tempfile.TemporaryDirectory() as temp:
            layout = resolve_install_layout(Path(temp) / "Container")
            self.assertEqual(layout["app"].name, "App")
            self.assertEqual(layout["updates"].name, "Updates")
            self.assertEqual(layout["app"].parent, layout["updates"].parent)
            source = (ROOT / "update_interface.py").read_text(encoding="utf-8")
            start = source.index("    def _selected_install_dir(self) -> Path:")
            end = source.index("    def open_install_folder", start)
            selector = source[start:end]
            self.assertLess(selector.index('if root:'), selector.index('if raw:'))
            self.assertIn('return resolve_install_layout(root)["app"]', selector)

    def test_container_layout_is_created_on_application_start_and_before_update(self):
        source = (ROOT / "app_initialization_interface.py").read_text(encoding="utf-8")
        self.assertIn("install_layout = ensure_install_layout(self.config[\"install_root_dir\"])", source)
        update_source = (ROOT / "update_interface.py").read_text(encoding="utf-8")
        start = update_source.index("    def _start_staged_update_install(")
        end = update_source.index("    def _install_staged_update_from_source", start)
        installer = update_source[start:end]
        self.assertIn("layout = ensure_install_layout(container_root)", installer)
        self.assertIn('self.config["updates_dir"] = str(layout["updates"])', installer)
        self.assertIn('self.config["install_dir"] = str(destination)', installer)

    def test_inno_setup_does_not_reuse_legacy_install_path_and_creates_siblings(self):
        installer = (ROOT / "INSTALLER.iss").read_text(encoding="utf-8")
        self.assertIn(r"DefaultDirName={localappdata}\Programs\ISH_Container\App", installer)
        self.assertIn("UsePreviousAppDir=no", installer)
        self.assertIn(r'Name: "{app}\..\Updates"', installer)
        self.assertIn(r'UninstallFilesDir={app}\..\Uninstall', installer)
        self.assertIn(r'Name: "{app}\..\Uninstall"', installer)

    def test_staged_update_modes_share_one_install_implementation(self):
        source = (ROOT / "update_interface.py").read_text(encoding="utf-8")
        start = source.index("    def _start_staged_update_install(")
        installer = source[start:]
        self.assertEqual(installer.count("launch_windows_directory_replacement("), 1)
        self.assertIn("staged_verified=True", installer)
        self.assertIn("self._start_staged_update_install(install_dir, source_process=True)", installer)
        self.assertIn("self._start_staged_update_install(install_dir, source_process=False)", installer)

    def test_move_current_build_copies_complete_onedir_folder(self):
        source = (ROOT / "update_interface.py").read_text(encoding="utf-8")
        start = source.index("    def install_current_build_to_selected_folder(self) -> None:")
        end = source.index("    def search_old_versions(self) -> None:", start)
        method = source[start:end]
        self.assertIn("shutil.copytree(current_dir, staged_dir)", method)
        self.assertIn("validate_app_directory(current_dir, APP_VERSION)", method)
        self.assertIn("launch_windows_directory_replacement(", method)
        self.assertNotIn("os.replace(temporary, target)", method)
        self.assertIn("_internal", method)

    def test_directory_updater_verifies_final_in_place_install_and_keeps_folder(self):
        helper = (ROOT / "updater_helper.py").read_text(encoding="utf-8")
        start = helper.index("def _directory_updater_script")
        end = helper.index("def launch_windows_directory_replacement", start)
        script = helper[start:end]
        self.assertIn("$stagedHash = VerifyFolder $StagedDir", script)
        self.assertNotIn("$copiedHash", script)
        self.assertIn("$ExeHash = VerifyFolder $TargetDir", script)
        self.assertIn("CopyDirectoryContents $TargetDir $BackupDir", script)
        self.assertIn("VerifyBackupCopy $TargetDir $BackupDir", script)
        self.assertIn("ClearDirectoryContents $TargetDir", script)
        self.assertIn("CopyDirectoryContents $StagedDir $TargetDir", script)
        self.assertNotIn("$TempDir", script)
        self.assertNotIn("$backupExe", script)
        self.assertNotIn("Move-Item -LiteralPath $TargetDir -Destination $BackupDir", script)
        self.assertIn("/MT:16", script)
        self.assertNotIn("/MT:8", script)
        self.assertIn("Stopwatch]::StartNew()", script)

    def test_directory_updater_uses_one_recursive_tree_scan(self):
        helper = (ROOT / "updater_helper.py").read_text(encoding="utf-8")
        start = helper.index("    function VerifyFolder([string]$Folder) {")
        end = helper.index("    function Rollback(", start)
        verify = helper[start:end]
        self.assertEqual(verify.count("Get-ChildItem -LiteralPath $Folder -Force -Recurse"), 1)
        self.assertIn("HashSet[string]", verify)
        self.assertIn("Фактический состав папки не совпадает", verify)

    def test_directory_updater_ignores_only_windows_shell_metadata(self):
        import hashlib
        import json
        from updater_helper import validate_app_directory

        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "ISH"
            internal = app / "_internal"
            internal.mkdir(parents=True)
            payloads = {
                "ISH.exe": b"fake exe",
                "_internal/python311.dll": b"python",
                "_internal/vcruntime140.dll": b"runtime",
                "_internal/vcruntime140_1.dll": b"runtime",
                "_internal/msvcp140.dll": b"runtime",
            }
            entries = []
            for relative, payload in payloads.items():
                target = app / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                entries.append({
                    "path": relative,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                })
            manifest = {
                "schema": 1,
                "version": "4.3.1",
                "entrypoint": "ISH.exe",
                "exe_sha256": hashlib.sha256(payloads["ISH.exe"]).hexdigest(),
                "files": entries,
            }
            (app / "build_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            (app / "desktop.ini").write_text("[.ShellClassInfo]", encoding="utf-8")
            (internal / "Thumbs.db").write_bytes(b"cache")
            (internal / "ehthumbs.db").write_bytes(b"cache")
            self.assertEqual(validate_app_directory(app, "4.3.1")["version"], "4.3.1")

            (internal / "unexpected.dll").write_bytes(b"unexpected")
            with self.assertRaisesRegex(RuntimeError, "лишние"):
                validate_app_directory(app, "4.3.1")

    def test_directory_updater_has_verified_folder_swap_and_rollback(self):
        helper = (ROOT / "updater_helper.py").read_text(encoding="utf-8")
        self.assertIn("validate_app_directory", helper)
        self.assertIn("launch_windows_directory_replacement", helper)
        self.assertIn("$BackupDir", helper)
        self.assertIn("Rollback", helper)
        self.assertIn("robocopy", helper)
        self.assertIn("MOYA_UPDATE_RECEIPT", helper)

    def test_package_generator_creates_manifest_and_zip_checksum(self):
        source = (ROOT / "package_onedir.py").read_text(encoding="utf-8")
        self.assertIn("build_manifest.json", source)
        self.assertIn("sha256", source)
        self.assertIn('stream.reconfigure(encoding="utf-8"', source)
        self.assertIn("ISH.zip", (ROOT / "updater.py").read_text(encoding="utf-8"))

    def test_runtime_crypto_self_test_passes_in_build_environment(self):
        from main import _packaged_import_self_test
        self.assertEqual(_packaged_import_self_test(), 0)

    def test_cryptography_is_declared_as_a_build_dependency(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        build_script = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("cryptography", requirements)
        self.assertIn("cffi>=2.0.0", requirements)
        self.assertIn("cryptography", build_script)
        self.assertIn("Verify active Python and install dependencies", workflow)

    def test_source_launcher_bootstraps_missing_cryptography(self):
        launcher = (ROOT / "START.bat").read_text(encoding="utf-8-sig")
        self.assertIn('import cryptography, cffi, _cffi_backend', launcher)
        self.assertIn('pip install --upgrade "cryptography>=42.0" "cffi>=2.0.0"', launcher)
        self.assertIn(":crypto_install_failed", launcher)

    def test_windows_version_resource_matches_release_version(self):
        source = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn("filevers=(4, 3, 1, 0)", source)
        self.assertIn("prodvers=(4, 3, 1, 0)", source)
        self.assertIn("FileVersion', '4.3.1'", source)
        self.assertIn("ProductVersion', '4.3.1'", source)



    def test_build_uses_actions_selected_python_interpreter(self):
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        self.assertIn("if defined MOYA_BUILD_PYTHON", build)
        self.assertIn("set \"PY=%MOYA_BUILD_PYTHON%\"", build)
        self.assertIn("-m pip install --upgrade -r requirements.txt", build)

    def test_workflow_uses_distinct_verified_name_and_node24_actions(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("Build Windows release — verified 4.3.1 onedir", workflow)
        self.assertIn("Audit python311.dll PE dependency tree on Windows", workflow)
        self.assertIn("runs-on: windows-2022", workflow)
        self.assertNotIn("build_patched_pyinstaller.py", workflow)

    def test_feature_branch_uses_single_push_ci_trigger(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("- 'feature/**'", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7.1.0", workflow)
        self.assertNotIn("actions/checkout@v4", workflow)
        self.assertNotIn("actions/setup-python@v5", workflow)
        self.assertNotIn("softprops/action-gh-release@v2", workflow)

    def test_workflow_publishes_only_after_onedir_smoke_test(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertLess(workflow.index("Verify app-local VC runtime DLLs are present"), workflow.index("Verify onedir EXE starts without Python on PATH"))
        self.assertLess(workflow.index("Verify onedir EXE starts without Python on PATH"), workflow.index("Create release or replace assets"))
        self.assertIn("ISH.zip.sha256", workflow)

    def test_self_improvement_retries_when_model_does_not_return_diff(self):
        source = (ROOT / "self_improvement_interface.py").read_text(encoding="utf-8")
        helper = (ROOT / "self_improvement.py").read_text(encoding="utf-8")
        self.assertIn("generate_validated_multi_file_unified_diff", source)
        self.assertIn("generate_validated_multi_file_unified_diff(", source)
        self.assertIn("apply_multi_file_unified_diff(sources, patch)", source)
        self.assertIn("max_attempts=3", source)
        self.assertIn("generation_attempt=attempt", source)
        self.assertIn("def generate_validated_unified_diff(", helper)
        self.assertIn("apply_unified_diff(original, diff, expected_path)", helper)
        self.assertIn("Не добавляй пояснений, Markdown или полный файл", helper)

    def test_portable_exe_is_checked_without_python_on_path(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("Verify onedir EXE starts without Python on PATH", workflow)
        self.assertIn("$startInfo.Environment['PATH'] = ", workflow)
        self.assertIn("'python311.dll'", workflow)



    def test_push_to_main_does_not_create_or_replace_a_release_without_hotfix_marker(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        release_step = workflow[workflow.index("- name: Create release or replace assets"): ]
        self.assertIn("startsWith(github.ref, 'refs/tags/')", release_step)
        self.assertIn("contains(github.event.head_commit.message, '[refresh-v4.3.1]')", release_step)
        self.assertIn("elseif ($env:GITHUB_REF -eq 'refs/heads/main')", release_step)
        self.assertIn("Refusing to create a new release from main", release_step)

    def test_hotfix_marker_refreshes_existing_v431_release_and_tag_only(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("RELEASE_TAG: ${{ startsWith(github.ref, 'refs/tags/') && github.ref_name || 'v4.3.1' }}", workflow)
        self.assertIn("- name: Update v4.3.1 tag to validated root source", workflow)
        self.assertIn("git push --force origin refs/tags/v4.3.1", workflow)
        self.assertIn('ISH 4.3.1 — onedir Windows 10 package" v4.3.1 $env:GITHUB_SHA', workflow)
        self.assertIn("git tag --force --annotate --message", workflow)
        self.assertIn('git config user.name "github-actions[bot]"', workflow)
        self.assertIn('git config user.email "41898282+github-actions[bot]@users.noreply.github.com"', workflow)
        self.assertLess(workflow.index("Create release or replace assets"), workflow.index("Update v4.3.1 tag to validated root source"))
    def test_windows10_script_checks_exact_target_os_without_python(self):
        script = (ROOT / "TEST_WINDOWS10.ps1").read_text(encoding="utf-8")
        self.assertIn("19045", script)
        self.assertIn("--self-test-imports", script)
        self.assertIn("PYTHONHOME", script)
        self.assertIn("PYTHONPATH", script)

    def test_windows_sandbox_is_bundled_and_required_for_proposal_tests(self):
        build = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8-sig")
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        workspace_source = (ROOT / "app_helpers.py").read_text(encoding="utf-8")
        selfdev = (ROOT / "self_improvement_interface.py").read_text(encoding="utf-8")
        testing = (ROOT / "improvement_testing.py").read_text(encoding="utf-8")
        sandbox = (ROOT / "windows_sandbox.py").read_text(encoding="utf-8")
        self.assertIn('--add-data "windows_sandbox.py;source_project"', build)
        self.assertIn('--add-data "supabase_backup.py;source_project"', build)
        self.assertIn('"supabase_backup.py"', workspace_source)
        self.assertIn('"tests/test_intelligent_memory.py"', workspace_source)
        self.assertIn('"tests/test_supabase_backup.py"', workspace_source)
        self.assertIn('"windows_sandbox.py"', workspace_source)
        self.assertIn("request_windows_sandbox_install", source)
        self.assertIn("record_windows_sandbox_install", selfdev)
        self.assertIn("record_windows_sandbox_install(result)", selfdev)
        self.assertIn("get_windows_sandbox_status", source)
        self.assertIn("<ProtectedClient>Enable</ProtectedClient>", sandbox)
        self.assertIn("<Networking>Disable</Networking>", sandbox)
        self.assertIn("<ClipboardRedirection>Disable</ClipboardRedirection>", sandbox)
        self.assertIn("if sandbox_executor is None:", testing)
        self.assertIn("_run_windows_sandbox", testing)
        self.assertIn("_is_windows_sandbox_guest", testing)
        self.assertIn("WDAGUtilityAccount", testing)
        self.assertIn("MOYA_WINDOWS_SANDBOX", testing)
        self.assertIn("return 3", testing)
        self.assertIn("allowed_names = {", sandbox)
        self.assertIn("_is_reparse_point", sandbox)
        self.assertNotIn('["-m", "unittest", "discover"', testing)


    def test_self_improvement_generates_and_tests_matching_multi_file_changes(self):
        main = (ROOT / "self_improvement_interface.py").read_text(encoding="utf-8")
        workspace = (ROOT / "app_helpers.py").read_text(encoding="utf-8")
        source = (ROOT / "self_improvement.py").read_text(encoding="utf-8")
        delivery = (ROOT / "improvement_delivery.py").read_text(encoding="utf-8")
        testing = (ROOT / "improvement_testing.py").read_text(encoding="utf-8")
        background = (ROOT / "background_developer.py").read_text(encoding="utf-8")
        self.assertIn("generate_validated_multi_file_unified_diff", main)
        self.assertIn("apply_multi_file_unified_diff", main)
        self.assertIn("related_test_path", main)
        self.assertIn("tests/test_*.py", main)
        self.assertIn("split_multi_file_unified_diff", source)
        self.assertIn("editable_test_files", source)
        self.assertIn("save_multi_change_bundle", delivery)
        self.assertIn("MAX_PROPOSAL_FILES", delivery)
        self.assertIn('if base_hash == "absent":', testing)
        self.assertIn("apply_multi_file_unified_diff", testing)
        self.assertIn("save_multi_change_bundle", background)
        self.assertIn('"tests/test_background_developer.py"', workspace)

    def test_multi_file_patch_is_never_applied_directly_or_sent_as_single_file_pr(self):
        update_source = (ROOT / "update_interface.py").read_text(encoding="utf-8")
        selfdev_source = (ROOT / "self_improvement_interface.py").read_text(encoding="utf-8")
        apply_start = update_source.index("    def apply_improvement(")
        apply_end = update_source.index("\n    def ", apply_start + 1)
        apply_method = update_source[apply_start:apply_end]
        pr_start = selfdev_source.index("    def create_improvement_pr(")
        pr_end = selfdev_source.find("\n    def ", pr_start + 1)
        if pr_end < 0:
            pr_end = len(selfdev_source)
        pr_method = selfdev_source[pr_start:pr_end]
        self.assertIn("split_multi_file_unified_diff", apply_method)
        self.assertIn("нельзя применить пакет к исходникам напрямую", apply_method.lower())
        self.assertIn("split_multi_file_unified_diff", pr_method)
        self.assertIn("if multi_file:", pr_method)
        self.assertIn("find_matching_tested_proposal_bundle", pr_method)
        self.assertIn("create_draft_pull_request_from_bundle", pr_method)
        self.assertIn("if multi_file and bundle_dir is not None:", pr_method)
        self.assertIn("create_draft_pull_request(", pr_method)

    def test_inno_setup_installer_version_is_431(self):
        installer = (ROOT / "INSTALLER.iss").read_text(encoding="utf-8")
        self.assertIn("AppVersion=4.3.1", installer)


if __name__ == "__main__":
    unittest.main()

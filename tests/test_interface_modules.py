# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import main
import app_configuration
import app_helpers
import app_startup
import app_initialization_interface
import app_lifecycle_interface
import backup_interface
import chat_interface
import cloud_interface
import memory_interface
import model_settings_interface
import plugin_interface
import research_interface
import self_improvement_interface
import settings_interface
import ui_components
import ui_pages_interface
import ui_theme_interface
import update_interface
import voice_interface


class InterfaceModuleTests(unittest.TestCase):
    def test_main_app_inherits_every_extracted_feature_mixin(self):
        mixins = (
            app_initialization_interface.ApplicationInitializationMixin,
            app_lifecycle_interface.AppLifecycleMixin,
            backup_interface.BackupInterfaceMixin,
            chat_interface.ChatInterfaceMixin,
            cloud_interface.CloudInterfaceMixin,
            memory_interface.MemoryInterfaceMixin,
            model_settings_interface.ModelSettingsMixin,
            plugin_interface.PluginInterfaceMixin,
            research_interface.ResearchInterfaceMixin,
            self_improvement_interface.SelfImprovementInterfaceMixin,
            settings_interface.SettingsInterfaceMixin,
            ui_pages_interface.UIPageMixin,
            ui_theme_interface.UIThemeMixin,
            update_interface.UpdateInterfaceMixin,
            voice_interface.VoiceInterfaceMixin,
        )
        for mixin in mixins:
            with self.subTest(mixin=mixin.__name__):
                self.assertTrue(issubclass(main.ISHApp, mixin))

    def test_remaining_ui_and_lifecycle_methods_are_owned_by_modules(self):
        self.assertIn("__init__", app_initialization_interface.ApplicationInitializationMixin.__dict__)
        self.assertIn("_build_windows_page", ui_pages_interface.UIPageMixin.__dict__)
        self.assertIn("_apply_theme", ui_theme_interface.UIThemeMixin.__dict__)
        self.assertIn("test_online", model_settings_interface.ModelSettingsMixin.__dict__)
        self.assertIn("on_close", app_lifecycle_interface.AppLifecycleMixin.__dict__)
        self.assertIn("save_resource_settings", settings_interface.SettingsInterfaceMixin.__dict__)

    def test_previous_feature_methods_remain_owned_by_their_modules(self):
        self.assertIn("_cloud_sync_worker", cloud_interface.CloudInterfaceMixin.__dict__)
        self.assertIn("_restore_backup_worker", backup_interface.BackupInterfaceMixin.__dict__)
        self.assertIn("_reply_worker", chat_interface.ChatInterfaceMixin.__dict__)
        self.assertIn("_research_worker", research_interface.ResearchInterfaceMixin.__dict__)
        self.assertIn("analyze_improvements", self_improvement_interface.SelfImprovementInterfaceMixin.__dict__)
        self.assertIn("check_for_updates", update_interface.UpdateInterfaceMixin.__dict__)
        self.assertIn("start_voice_input", voice_interface.VoiceInterfaceMixin.__dict__)
        self.assertIn("add_memory", memory_interface.MemoryInterfaceMixin.__dict__)
        self.assertIn("create_skill", plugin_interface.PluginInterfaceMixin.__dict__)
        self.assertIn("save_settings", settings_interface.SettingsInterfaceMixin.__dict__)

    def test_runtime_globals_are_bound_in_new_modules(self):
        self.assertIs(app_initialization_interface.APP_VERSION, main.APP_VERSION)
        self.assertIs(ui_pages_interface.tk, main.tk)
        self.assertIs(model_settings_interface.normalize_url, main.normalize_url)
        self.assertIs(app_lifecycle_interface.DATA_DIR, main.DATA_DIR)

    def test_application_support_modules_are_reexported_by_main(self):
        self.assertIs(main.DEFAULT_CONFIG, app_configuration.DEFAULT_CONFIG)
        self.assertIs(main.user_data_dir, app_configuration.user_data_dir)
        self.assertIs(main.read_attachment, app_helpers.read_attachment)
        self.assertIs(main.prepare_source_workspace, app_helpers.prepare_source_workspace)
        self.assertIs(main.main, app_startup.main)

    def test_custom_checkbox_is_reexported_from_main(self):
        self.assertIs(main.PurpleCheckbox, ui_components.PurpleCheckbox)

if __name__ == "__main__":
    unittest.main(verbosity=2)

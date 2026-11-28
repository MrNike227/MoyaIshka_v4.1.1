# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from unittest import mock

import cloud_sync
import main as main_module
import secure_storage


class SecureStorageCompatibilityTests(unittest.TestCase):
    def test_main_and_cloud_keep_legacy_dpapi_symbols(self):
        self.assertIs(main_module.DATA_BLOB, secure_storage.DATA_BLOB)
        self.assertIs(main_module.dpapi_transform, secure_storage.dpapi_transform)
        self.assertIs(main_module.protect_api_key, secure_storage.protect_api_key)
        self.assertIs(main_module.unprotect_api_key, secure_storage.unprotect_api_key)
        self.assertIs(main_module.unprotect_github_pr_token, secure_storage.unprotect_github_pr_token)
        self.assertIs(cloud_sync._DATA_BLOB, secure_storage.DATA_BLOB)

    def test_cloud_sync_keeps_its_session_specific_dpapi_label(self):
        with mock.patch.object(cloud_sync, "_dpapi_transform", return_value=b"result") as transform:
            self.assertEqual(cloud_sync._dpapi(b"input", True), b"result")
        transform.assert_called_once_with(b"input", True, description="ISH cloud session")


class DPAPIPrimitiveTests(unittest.TestCase):
    def test_dpapi_is_explicitly_unavailable_off_windows(self):
        fake_os = SimpleNamespace(name="posix")
        with mock.patch.object(secure_storage, "os", fake_os):
            with self.assertRaisesRegex(OSError, "только в Windows"):
                secure_storage.dpapi_transform(b"secret", True)

    def test_protect_api_key_keeps_legacy_development_fallback_off_windows(self):
        fake_os = SimpleNamespace(name="posix")
        with mock.patch.object(secure_storage, "os", fake_os):
            self.assertEqual(secure_storage.protect_api_key("local-key"), ("", "local-key"))
            self.assertEqual(secure_storage.protect_api_key(""), ("", ""))

    def test_protect_api_key_uses_dpapi_on_windows(self):
        fake_os = SimpleNamespace(name="nt")
        with mock.patch.object(secure_storage, "os", fake_os), mock.patch.object(
            secure_storage, "dpapi_transform", return_value=b"ciphertext",
        ) as transform:
            protected, plaintext = secure_storage.protect_api_key("secret-key")
        self.assertEqual(base64.b64decode(protected), b"ciphertext")
        self.assertEqual(plaintext, "")
        transform.assert_called_once_with(b"secret-key", True, description="ISH API key")

    def test_unprotect_api_key_reads_dpapi_value_on_windows(self):
        fake_os = SimpleNamespace(name="nt")
        config = {"online_api_key_protected": base64.b64encode(b"ciphertext").decode("ascii"), "online_api_key_plain": "stale-plaintext"}
        with mock.patch.object(secure_storage, "os", fake_os), mock.patch.object(
            secure_storage, "dpapi_transform", return_value=b"decoded-key",
        ) as transform:
            result = secure_storage.unprotect_api_key(config)
        self.assertEqual(result, "decoded-key")
        transform.assert_called_once_with(b"ciphertext", False)

    def test_unprotect_api_key_does_not_fall_back_to_plaintext_when_dpapi_fails(self):
        fake_os = SimpleNamespace(name="nt")
        config = {"online_api_key_protected": base64.b64encode(b"ciphertext").decode("ascii"), "online_api_key_plain": "stale-plaintext"}
        with mock.patch.object(secure_storage, "os", fake_os), mock.patch.object(
            secure_storage, "dpapi_transform", side_effect=OSError("bad DPAPI data"),
        ):
            self.assertEqual(secure_storage.unprotect_api_key(config), "")

    def test_unprotect_helpers_keep_legacy_plain_values_off_windows(self):
        fake_os = SimpleNamespace(name="posix")
        with mock.patch.object(secure_storage, "os", fake_os):
            self.assertEqual(secure_storage.unprotect_api_key({"online_api_key_plain": "legacy-key"}), "legacy-key")
            self.assertEqual(secure_storage.unprotect_github_pr_token({"github_pr_token_plain": "legacy-token"}), "legacy-token")

    def test_unprotect_github_token_uses_dpapi_on_windows(self):
        fake_os = SimpleNamespace(name="nt")
        config = {"github_pr_token_protected": base64.b64encode(b"ciphertext").decode("ascii")}
        with mock.patch.object(secure_storage, "os", fake_os), mock.patch.object(
            secure_storage, "dpapi_transform", return_value=b"github-token",
        ):
            self.assertEqual(secure_storage.unprotect_github_pr_token(config), "github-token")


if __name__ == "__main__":
    unittest.main(verbosity=2)

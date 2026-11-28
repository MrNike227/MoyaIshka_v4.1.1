# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class CloudInterfaceMixin:
    # ---------- cloud vault and resource-aware background work ----------
    @staticmethod
    def _is_google_drive_session_ready(package: dict[str, Any] | None) -> bool:
        package = package or {}
        session = package.get("session", {}) if isinstance(package.get("session"), dict) else {}
        return bool(package.get("client_id") and package.get("client_secret") and package.get("e2e_passphrase") and session.get("refresh_token"))

    def _any_cloud_session_ready(self) -> bool:
        return bool(self.google_drive_session_ready or self.cloud_session_ready)

    def _preferred_cloud_package(self) -> dict[str, Any] | None:
        # Google Drive is always primary. Supabase is the optional mirror/failover.
        if self.google_drive_session_ready:
            return dict(self.google_drive_session)
        if self.cloud_session_ready:
            package = dict(self.cloud_session)
            package["provider"] = "supabase"
            return package
        return None

    def _remember_cloud_package(self, package: dict[str, Any]) -> None:
        provider = str(package.get("provider", "supabase"))
        if provider == "google_drive":
            self.google_drive_session = dict(package)
            self.google_drive_session_ready = self._is_google_drive_session_ready(self.google_drive_session)
            try:
                save_protected_session(GOOGLE_DRIVE_SESSION_PATH, self.google_drive_session)
            except Exception:
                pass
        else:
            self.cloud_session = dict(package)
            self.cloud_session_ready = bool(self.cloud_session.get("session", {}).get("access_token") and self.cloud_session.get("e2e_passphrase"))
            try:
                save_protected_session(CLOUD_SESSION_PATH, self.cloud_session)
            except Exception:
                pass

    def google_drive_connect(self) -> None:
        client_id = self.google_drive_client_id_var.get().strip()
        client_secret = self.google_drive_client_secret_var.get().strip()
        passphrase = self.google_drive_e2e_password_var.get()
        if not client_id or not client_secret:
            messagebox.showwarning("Google Drive", "Сначала укажи OAuth Client ID и Client Secret типа Desktop app. Инструкция находится в GOOGLE_DRIVE_SETUP_RU.md.")
            return
        if len(passphrase) < 10:
            messagebox.showwarning("Сквозное шифрование", "Пароль E2E должен содержать не менее 10 символов. Сохрани его в менеджере паролей — без него данные нельзя расшифровать.")
            return
        try:
            limit = max(1, min(int(self.google_drive_limit_var.get()), 10))
        except (ValueError, AttributeError):
            limit = 10
        self.config["google_drive_client_id"] = client_id
        self.config["google_drive_storage_limit_gb"] = limit
        atomic_json_save(CONFIG_PATH, self.config)
        self.google_drive_status_var.set("Открываю браузер для безопасного подключения Google…")
        threading.Thread(target=self._google_drive_auth_worker,
                         args=(client_id, client_secret, passphrase), daemon=True).start()

    def _google_drive_auth_worker(self, client_id: str, client_secret: str, passphrase: str) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            session = GoogleDriveVaultClient.authorize(client_id, client_secret)
            package = {
                "provider": "google_drive", "client_id": client_id,
                "client_secret": client_secret, "e2e_passphrase": passphrase,
                "session": session,
            }
            client = GoogleDriveVaultClient(client_id, client_secret, session)
            row = client.get_vault()
            remote = decrypt_vault(row, passphrase) if row else None
            package["session"] = client.session
            revision = str(row.get("updated_at", "")) if row else ""
            self.events.put(("google_drive_auth_success", (package, remote, revision)))
        except Exception as exc:
            self.events.put(("google_drive_auth_error", str(exc)))

    def google_drive_disconnect(self) -> None:
        if not self.google_drive_session_ready:
            self.google_drive_status_var.set("Google Drive не подключён.")
            return
        if not messagebox.askyesno("Отключить Google Drive", "Отключить Google Drive на этом компьютере? Файлы в Google Drive останутся нетронутыми."):
            return
        delete_protected_session(GOOGLE_DRIVE_SESSION_PATH)
        self.google_drive_session = {}
        self.google_drive_session_ready = False
        self.google_drive_status_var.set("Google Drive отключён на этом ПК. Облачные файлы не удалены.")
        if self.cloud_session_ready:
            self.cloud_status_var.set("Supabase продолжает работать как основное доступное облако.")
        elif self.cloud_sync_periodic_id:
            try:
                self.root.after_cancel(self.cloud_sync_periodic_id)
            except Exception:
                pass
            self.cloud_sync_periodic_id = None

    def _cloud_bundle_from_fields(self) -> dict[str, Any]:
        return {
            "project_url": self.cloud_url_var.get().strip(),
            "publishable_key": self.cloud_publishable_key_var.get().strip(),
            "email": self.cloud_email_var.get().strip(),
            "account_password": self.cloud_account_password_var.get(),
            "e2e_passphrase": self.cloud_e2e_password_var.get(),
        }

    def _save_cloud_bundle(self, bundle: dict[str, Any], session: dict[str, Any]) -> None:
        self.cloud_session = {
            "project_url": str(bundle.get("project_url", "")),
            "publishable_key": str(bundle.get("publishable_key", "")),
            "email": str(bundle.get("email", "")),
            "e2e_passphrase": str(bundle.get("e2e_passphrase", "")),
            "session": dict(session),
        }
        self.cloud_session_ready = bool(self.cloud_session["session"].get("access_token") and self.cloud_session["e2e_passphrase"])
        self.config.update({
            "cloud_url": self.cloud_session["project_url"],
            "cloud_publishable_key": self.cloud_session["publishable_key"],
            "cloud_email": self.cloud_session["email"],
            "cloud_auto_sync": bool(self.cloud_auto_sync_var.get()) if hasattr(self, "cloud_auto_sync_var") else True,
            "cloud_auto_sync_user_configured": True,
        })
        atomic_json_save(CONFIG_PATH, self.config)
        if self.cloud_session_ready:
            try:
                save_protected_session(CLOUD_SESSION_PATH, self.cloud_session)
            except Exception as exc:
                self.cloud_status_var.set(f"Сессия активна до закрытия приложения, но не удалось сохранить её через DPAPI: {exc}")

    def save_cloud_preferences(self) -> None:
        self.config["cloud_url"] = self.cloud_url_var.get().strip()
        self.config["cloud_publishable_key"] = self.cloud_publishable_key_var.get().strip()
        self.config["cloud_email"] = self.cloud_email_var.get().strip()
        self.config["cloud_auto_sync"] = bool(self.cloud_auto_sync_var.get())
        self.config["cloud_auto_sync_user_configured"] = True
        if hasattr(self, "google_drive_client_id_var"):
            self.config["google_drive_client_id"] = self.google_drive_client_id_var.get().strip()
            try:
                self.config["google_drive_storage_limit_gb"] = max(1, min(int(self.google_drive_limit_var.get()), 10))
            except (ValueError, AttributeError):
                self.config["google_drive_storage_limit_gb"] = 10
        atomic_json_save(CONFIG_PATH, self.config)
        self.cloud_status_var.set("Параметры облака сохранены. Пароли не сохраняются в открытом виде.")
        if self.config["cloud_auto_sync"] and self._any_cloud_session_ready():
            self._schedule_cloud_sync_periodic()
        elif self.cloud_sync_periodic_id:
            try:
                self.root.after_cancel(self.cloud_sync_periodic_id)
            except Exception:
                pass
            self.cloud_sync_periodic_id = None

    def cloud_sign_up(self) -> None:
        bundle = self._cloud_bundle_from_fields()
        if not bundle["email"] or not bundle["account_password"] or not bundle["e2e_passphrase"]:
            messagebox.showwarning("Облачный аккаунт", "Заполни URL, публичный ключ Supabase, почту и оба пароля.")
            return
        if len(bundle["e2e_passphrase"]) < 10:
            messagebox.showwarning("Сквозное шифрование", "Пароль шифрования должен содержать не менее 10 символов. Не теряй его: без него восстановить облачную копию невозможно.")
            return
        bundle.update({"action": "signup"})
        self.cloud_status_var.set("Создаю аккаунт Supabase…")
        threading.Thread(target=self._cloud_auth_worker, args=(bundle,), daemon=True).start()

    def cloud_sign_in(self) -> None:
        bundle = self._cloud_bundle_from_fields()
        if not all(bundle.get(key) for key in ("project_url", "publishable_key", "email", "account_password", "e2e_passphrase")):
            messagebox.showwarning("Облако", "Заполни URL проекта, публичный ключ, почту, пароль аккаунта и пароль шифрования.")
            return
        if len(bundle["e2e_passphrase"]) < 10:
            messagebox.showwarning("Сквозное шифрование", "Пароль шифрования должен содержать не менее 10 символов. Это отдельный ключ доступа к данным.")
            return
        bundle.update({"action": "signin"})
        self.cloud_status_var.set("Вхожу в Supabase и проверяю зашифрованное облако…")
        threading.Thread(target=self._cloud_auth_worker, args=(bundle,), daemon=True).start()

    def _cloud_auth_worker(self, bundle: dict[str, Any]) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            client = SupabaseCloudClient(bundle["project_url"], bundle["publishable_key"])
            if bundle.get("action") == "signup":
                signup = client.sign_up(bundle["email"], bundle["account_password"])
                if signup.get("needs_email_confirmation"):
                    self.events.put(("cloud_signup_pending", "Supabase создал запрос регистрации. Подтверди адрес электронной почты в письме, затем нажми «Войти и синхронизировать»."))
                    return
                if not client.session.get("access_token"):
                    client.sign_in(bundle["email"], bundle["account_password"])
            else:
                client.sign_in(bundle["email"], bundle["account_password"])
            row = client.get_vault()
            remote_payload = decrypt_vault(row, bundle["e2e_passphrase"]) if row else None
            session_package = {
                "project_url": bundle["project_url"],
                "publishable_key": bundle["publishable_key"],
                "email": bundle["email"],
                "e2e_passphrase": bundle["e2e_passphrase"],
                "session": client.session,
            }
            self.events.put(("cloud_auth_success", (session_package, remote_payload, row.get("updated_at") if row else None)))
        except Exception as exc:
            self.events.put(("cloud_auth_error", str(exc)))

    def cloud_sync_now(self) -> None:
        if hasattr(self, "cloud_auto_sync_var"):
            self.config["cloud_auto_sync"] = bool(self.cloud_auto_sync_var.get())
        self.config["cloud_auto_sync_user_configured"] = True
        self.config["cloud_url"] = self.cloud_url_var.get().strip() if hasattr(self, "cloud_url_var") else str(self.config.get("cloud_url", ""))
        self.config["cloud_publishable_key"] = self.cloud_publishable_key_var.get().strip() if hasattr(self, "cloud_publishable_key_var") else str(self.config.get("cloud_publishable_key", ""))
        self.config["cloud_email"] = self.cloud_email_var.get().strip() if hasattr(self, "cloud_email_var") else str(self.config.get("cloud_email", ""))
        atomic_json_save(CONFIG_PATH, self.config)
        if not self._any_cloud_session_ready():
            messagebox.showinfo("Облако не подключено", "Сначала подключи Google Drive. Supabase можно подключить отдельно как резервное облако.")
            return
        self._start_cloud_sync(force=True)

    def cloud_sign_out(self) -> None:
        if not self.cloud_session_ready:
            self.cloud_status_var.set("Облако не подключено.")
            return
        if not messagebox.askyesno("Отключить облако", "Отключить синхронизацию на этом компьютере? Зашифрованная копия в Supabase останется нетронутой."):
            return
        delete_protected_session(CLOUD_SESSION_PATH)
        self.cloud_session = {}
        self.cloud_session_ready = False
        self.config["cloud_auto_sync"] = bool(self.google_drive_session_ready)
        self.config["cloud_auto_sync_user_configured"] = True
        if hasattr(self, "google_drive_client_id_var"):
            self.config["google_drive_client_id"] = self.google_drive_client_id_var.get().strip()
            try:
                self.config["google_drive_storage_limit_gb"] = max(1, min(int(self.google_drive_limit_var.get()), 10))
            except (ValueError, AttributeError):
                self.config["google_drive_storage_limit_gb"] = 10
        atomic_json_save(CONFIG_PATH, self.config)
        self.cloud_auto_sync_var.set(bool(self.google_drive_session_ready))
        self.cloud_status_var.set("Supabase отключён на этом компьютере. Данные в Supabase не удалены.")
        if self.google_drive_session_ready:
            self.google_drive_status_var.set("Google Drive продолжает работать как основное облако.")
            self._schedule_cloud_sync_periodic()

    def _build_cloud_snapshot(self) -> dict[str, Any]:
        conversations: list[dict[str, Any]] = []
        for conversation in self.store.list_conversations():
            item = {key: conversation[key] for key in ("id", "title", "created_at", "updated_at")}
            item["messages"] = [
                {key: row[key] for key in ("sync_id", "role", "content", "source", "created_at")}
                for row in self.store.get_messages(str(conversation["id"]))
            ]
            conversations.append(item)
        safe_preference_keys = (
            "assistant_name", "role", "personality", "style", "instructions", "mode",
            "online_url", "online_model", "ollama_url", "ollama_model", "temperature",
            "theme", "font_family", "font_size", "auto_memory", "memory_semantic_enabled", "memory_embedding_model", "voice_tts", "voice_engine",
            "tts_voice_id", "plugins_enabled", "web_search_enabled", "auto_search_current",
            "use_research_library", "research_auto_enabled", "research_topics",
            "research_interval_hours", "research_results_limit", "research_fetch_pages",
        )
        preferences = {key: self.config.get(key) for key in safe_preference_keys if key in self.config}
        return {
            "schema_version": 1,
            "exported_at": now_iso(),
            "config_modified_at": str(self.config.get("cloud_modified_at", "")),
            "preferences": preferences,
            "memory": [str(item)[:500] for item in self.config.get("memory", []) if isinstance(item, str)][:2000],
            "memory_metadata": list(self.config.get("memory_metadata", []))[:2000],
            "conversations": conversations,
            "research": list(self.research_library.items[-1000:]),
        }

    def _merge_cloud_snapshot(self, snapshot: dict[str, Any]) -> tuple[int, int, int]:
        if not isinstance(snapshot, dict) or int(snapshot.get("schema_version", 0)) != 1:
            raise CloudSyncError("Структура облачной копии не поддерживается.")
        conversations = snapshot.get("conversations", [])
        if not isinstance(conversations, list) or len(conversations) > 10000:
            raise CloudSyncError("В облачной копии слишком много диалогов или неверный формат.")
        new_messages = 0
        new_conversations = 0
        db = self.store.db
        db.execute("BEGIN")
        try:
            for conv in conversations:
                if not isinstance(conv, dict):
                    continue
                cid = str(conv.get("id", ""))[:80]
                if not cid:
                    continue
                title = str(conv.get("title", "Новый диалог"))[:100]
                created = str(conv.get("created_at", now_iso()))[:64]
                updated = str(conv.get("updated_at", created))[:64]
                cur = db.execute("INSERT OR IGNORE INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)", (cid, title, created, updated))
                new_conversations += max(0, cur.rowcount)
                local = db.execute("SELECT updated_at FROM conversations WHERE id=?", (cid,)).fetchone()
                if local and updated > str(local["updated_at"]):
                    db.execute("UPDATE conversations SET title=?,updated_at=? WHERE id=?", (title, updated, cid))
                messages = conv.get("messages", [])
                if not isinstance(messages, list):
                    continue
                for message in messages[:100000]:
                    if not isinstance(message, dict):
                        continue
                    role = str(message.get("role", ""))
                    if role not in {"user", "assistant", "system"}:
                        continue
                    content = str(message.get("content", ""))
                    if len(content) > 300000:
                        content = content[:300000]
                    sync_id = str(message.get("sync_id", ""))[:80] or uuid.uuid4().hex
                    source = str(message.get("source", ""))[:120]
                    created_at = str(message.get("created_at", updated))[:64]
                    cur = db.execute(
                        "INSERT OR IGNORE INTO messages(conversation_id,role,content,source,created_at,sync_id) VALUES(?,?,?,?,?,?)",
                        (cid, role, content, source, created_at, sync_id),
                    )
                    new_messages += max(0, cur.rowcount)
            db.commit()
        except Exception:
            db.rollback()
            raise

        local_memory = self.config.get("memory", []) if isinstance(self.config.get("memory", []), list) else []
        remote_memory = snapshot.get("memory", []) if isinstance(snapshot.get("memory", []), list) else []
        merged_memory, merged_metadata = merge_memory_data(
            local_memory, self.config.get("memory_metadata", []),
            remote_memory, snapshot.get("memory_metadata", []),
        )
        self.config["memory"] = merged_memory
        self.config["memory_metadata"] = merged_metadata

        remote_config_time = str(snapshot.get("config_modified_at", ""))
        local_config_time = str(self.config.get("cloud_modified_at", ""))
        preferences = snapshot.get("preferences", {})
        if isinstance(preferences, dict) and remote_config_time and remote_config_time > local_config_time:
            allowed = set(self._cloud_preference_keys())
            for key, value in preferences.items():
                if key in allowed:
                    self.config[key] = value
            self.config["cloud_modified_at"] = remote_config_time
            try:
                self._reload_settings_controls()
            except Exception:
                pass
        atomic_json_save(CONFIG_PATH, self.config)
        docs = snapshot.get("research", [])
        if not isinstance(docs, list):
            docs = []
        added_docs = self.research_library.add_documents([d for d in docs[:1000] if isinstance(d, dict)])
        self._refresh_chat_list()
        if self.current_chat_id not in self.store.conversation_ids():
            self.current_chat_id = self.store.ensure_conversation()
        self._render_current_chat()
        self._refresh_memory_list()
        self._refresh_research_list()
        return new_conversations, new_messages, added_docs

    @staticmethod
    def _cloud_preference_keys() -> tuple[str, ...]:
        return (
            "assistant_name", "role", "personality", "style", "instructions", "mode",
            "online_url", "online_model", "ollama_url", "ollama_model", "temperature",
            "theme", "font_family", "font_size", "auto_memory", "memory_semantic_enabled", "memory_embedding_model", "voice_tts", "voice_engine",
            "tts_voice_id", "plugins_enabled", "web_search_enabled", "auto_search_current",
            "use_research_library", "research_auto_enabled", "research_topics",
            "research_interval_hours", "research_results_limit", "research_fetch_pages",
        )

    def _schedule_cloud_sync(self) -> None:
        if not bool(self.config.get("cloud_auto_sync", False)) or not self._any_cloud_session_ready():
            return
        if self.cloud_sync_busy:
            self.cloud_sync_dirty = True
            return
        if self.cloud_sync_after_id:
            try:
                self.root.after_cancel(self.cloud_sync_after_id)
            except Exception:
                pass
        self.cloud_sync_after_id = self.root.after(5000, self._start_cloud_sync)

    def _cloud_client(self, session_package: dict[str, Any] | None = None):
        bundle = session_package or self._preferred_cloud_package() or self.cloud_session
        if str(bundle.get("provider", "supabase")) == "google_drive":
            return GoogleDriveVaultClient(
                str(bundle.get("client_id", "")), str(bundle.get("client_secret", "")),
                dict(bundle.get("session", {})),
            )
        return SupabaseCloudClient(
            str(bundle.get("project_url") or self.config.get("cloud_url", "")),
            str(bundle.get("publishable_key") or self.config.get("cloud_publishable_key", "")),
            dict(bundle.get("session", {})),
        )

    def _mirror_to_supabase_backup(self, snapshot: dict[str, Any], backup_package: dict[str, Any] | None) -> str:
        if not backup_package:
            return ""
        try:
            client = self._cloud_client(backup_package)
            row = client.get_vault()
            encrypted = encrypt_vault(snapshot, str(backup_package.get("e2e_passphrase", "")))
            if not row:
                if not client.create_vault(encrypted):
                    return "резерв Supabase изменился одновременно; повтори синхронизацию"
                return "резервная копия Supabase обновлена"
            try:
                remote = decrypt_vault(row, str(backup_package.get("e2e_passphrase", "")))
                if snapshot_digest(remote) == snapshot_digest(snapshot):
                    return "резерв Supabase уже актуален"
            except CloudSyncError:
                return "резерв Supabase не обновлён: данные не удалось безопасно расшифровать"
            if client.update_vault(encrypted, str(row.get("updated_at", ""))):
                return "резервная копия Supabase обновлена"
            return "резерв Supabase изменился одновременно; повтори синхронизацию"
        except Exception as exc:
            return f"резерв Supabase временно недоступен: {exc}"

    def _enforce_google_drive_soft_quota(self, client: GoogleDriveVaultClient, encrypted: dict[str, Any]) -> tuple[int, int]:
        """Enforce the app's own folder budget, not the whole Google account quota."""
        limit_gb = max(1, min(int(self.config.get("google_drive_storage_limit_gb", 10) or 10), 10))
        limit_bytes = limit_gb * 1024 * 1024 * 1024
        usage = client.get_app_folder_usage()
        current = client.get_vault()
        old_size = int(current.get("size", 0) or 0) if current else 0
        new_size = len(json.dumps(encrypted, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        projected = max(0, usage - old_size) + new_size
        if projected > limit_bytes:
            raise CloudSyncError(
                f"Достигнут мягкий лимит папки ИИшки в Google Drive ({limit_gb} ГБ). "
                "Новые данные не загружены и не удалены. Увеличь лимит, освободи место в папке или подключи резервное облако."
            )
        return projected, limit_bytes

    def _start_cloud_sync(self, force: bool = False) -> None:
        self.cloud_sync_after_id = None
        if self._database_restore_in_progress:
            self.cloud_sync_dirty = True
            return
        package = self._preferred_cloud_package()
        if not package:
            if force and hasattr(self, "cloud_status_var"):
                self.cloud_status_var.set("Сначала подключи Google Drive или резервный Supabase.")
            return
        if not force and not bool(self.config.get("cloud_auto_sync", False)):
            return
        if self.cloud_sync_busy:
            self.cloud_sync_dirty = True
            return
        snapshot = self._build_cloud_snapshot()
        backup = dict(self.cloud_session) if (package.get("provider") == "google_drive" and self.cloud_session_ready) else None
        if backup:
            backup["provider"] = "supabase"
        self.cloud_sync_busy = True
        self.cloud_sync_dirty = False
        if hasattr(self, "cloud_status_var"):
            self.cloud_status_var.set("Синхронизирую зашифрованные данные: Google Drive — основное облако" + (", Supabase — резервная копия…" if backup else "…"))
        threading.Thread(target=self._cloud_sync_worker, args=(snapshot, package, backup), daemon=True).start()

    def _cloud_sync_worker(self, snapshot: dict[str, Any], session_package: dict[str, Any], backup_package: dict[str, Any] | None = None) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        provider = str(session_package.get("provider", "supabase"))
        try:
            if not self.resource_governor.wait_for_background_slot(max_wait_seconds=900):
                raise CloudSyncError("Синхронизация отложена: компьютер занят или достигнут лимит ресурсов.")
            client = self._cloud_client(session_package)
            row = client.get_vault()
            updated_session = dict(session_package)
            updated_session["session"] = client.session
            if row:
                remote = decrypt_vault(row, str(session_package.get("e2e_passphrase", "")))
                if snapshot_digest(snapshot) == snapshot_digest(remote):
                    backup_note = self._mirror_to_supabase_backup(snapshot, backup_package) if provider == "google_drive" else ""
                    status = "Google Drive синхронизирован; облачная копия уже актуальна" if provider == "google_drive" else "Облачная копия уже актуальна — повторная загрузка не нужна"
                    if backup_note:
                        status += f"; {backup_note}"
                    self.events.put(("cloud_sync_done", (updated_session, status)))
                else:
                    self.events.put(("cloud_remote_data", (remote, str(row.get("updated_at", "")), updated_session)))
            else:
                # If the primary Google Drive is empty, recover from the optional Supabase mirror first.
                if provider == "google_drive" and backup_package:
                    backup_client = self._cloud_client(backup_package)
                    backup_row = backup_client.get_vault()
                    if backup_row:
                        remote = decrypt_vault(backup_row, str(backup_package.get("e2e_passphrase", "")))
                        self.events.put(("cloud_remote_data", (remote, "__new__", updated_session)))
                        return
                encrypted = encrypt_vault(snapshot, str(session_package.get("e2e_passphrase", "")))
                if provider == "google_drive":
                    self._enforce_google_drive_soft_quota(client, encrypted)
                created = client.create_vault(encrypted)
                if created:
                    backup_note = self._mirror_to_supabase_backup(snapshot, backup_package) if provider == "google_drive" else ""
                    updated_session["session"] = client.session
                    status = "Создана первая зашифрованная копия в Google Drive" if provider == "google_drive" else "Создана первая зашифрованная облачная копия"
                    if backup_note:
                        status += f"; {backup_note}"
                    self.events.put(("cloud_sync_done", (updated_session, status)))
                else:
                    self.events.put(("cloud_sync_conflict", (updated_session, "Облачная запись появилась с другого устройства. Повтори синхронизацию.")))
        except Exception as primary_exc:
            # Google Drive is primary; Supabase is a failover and mirror if connected.
            if provider == "google_drive" and backup_package:
                try:
                    backup_client = self._cloud_client(backup_package)
                    row = backup_client.get_vault()
                    if row:
                        remote = decrypt_vault(row, str(backup_package.get("e2e_passphrase", "")))
                        if snapshot_digest(snapshot) == snapshot_digest(remote):
                            self.events.put(("cloud_sync_done", (backup_package, f"Google Drive временно недоступен; Supabase использован как резерв. {primary_exc}")))
                        else:
                            self.events.put(("cloud_remote_data", (remote, str(row.get("updated_at", "")), backup_package)))
                    else:
                        encrypted = encrypt_vault(snapshot, str(backup_package.get("e2e_passphrase", "")))
                        if backup_client.create_vault(encrypted):
                            self.events.put(("cloud_sync_done", (backup_package, f"Google Drive недоступен; создана копия в резервном Supabase. {primary_exc}")))
                        else:
                            self.events.put(("cloud_sync_conflict", (backup_package, "Не удалось записать резервную копию: запись изменилась одновременно.")))
                except Exception as backup_exc:
                    self.events.put(("cloud_sync_error", f"Google Drive: {primary_exc}; резерв Supabase: {backup_exc}"))
            else:
                self.events.put(("cloud_sync_error", str(primary_exc)))

    def _finish_google_backup_mirror_worker(self, snapshot: dict[str, Any], session_package: dict[str, Any], counts: tuple[int, int, int]) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        backup = dict(self.cloud_session) if self.cloud_session_ready else None
        note = self._mirror_to_supabase_backup(snapshot, backup)
        self.events.put(("cloud_sync_done", (session_package,
            f"Google Drive синхронизирован; диалогов +{counts[0]}, сообщений +{counts[1]}, источников +{counts[2]}; {note}.")))

    def _cloud_upload_worker(self, snapshot: dict[str, Any], session_package: dict[str, Any], expected_updated_at: str) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        provider = str(session_package.get("provider", "supabase"))
        try:
            if not self.resource_governor.wait_for_background_slot(max_wait_seconds=900):
                raise CloudSyncError("Загрузка в облако отложена: компьютер занят или достигнут лимит ресурсов.")
            client = self._cloud_client(session_package)
            encrypted = encrypt_vault(snapshot, str(session_package.get("e2e_passphrase", "")))
            drive_usage_note = ""
            if provider == "google_drive":
                projected, limit_bytes = self._enforce_google_drive_soft_quota(client, encrypted)
                drive_usage_note = f" · папка ИИшки: {projected / (1024**2):.1f} МБ из {limit_bytes / (1024**3):.0f} ГБ"
            if provider == "google_drive" and expected_updated_at == "__new__":
                updated = client.create_vault(encrypted)
            else:
                updated = client.update_vault(encrypted, expected_updated_at)
            package = dict(session_package)
            package["session"] = client.session
            if updated:
                extra = ""
                if provider == "google_drive" and self.cloud_session_ready:
                    backup = dict(self.cloud_session)
                    backup["provider"] = "supabase"
                    extra = "; " + self._mirror_to_supabase_backup(snapshot, backup)
                label = "Google Drive" if provider == "google_drive" else "облачное хранилище"
                self.events.put(("cloud_sync_done", (package, f"Изменения объединены и сохранены в {label}{extra}{drive_usage_note}.")))
            else:
                self.events.put(("cloud_sync_conflict", (package, "Облако изменилось с другого устройства во время синхронизации. Повтори синхронизацию: локальные данные не удалены.")))
        except Exception as exc:
            self.events.put(("cloud_sync_error", str(exc)))

    def _schedule_cloud_sync_periodic(self) -> None:
        if self.cloud_sync_periodic_id:
            try:
                self.root.after_cancel(self.cloud_sync_periodic_id)
            except Exception:
                pass
            self.cloud_sync_periodic_id = None
        if self._any_cloud_session_ready() and bool(self.config.get("cloud_auto_sync", False)):
            interval = max(1, min(int(self.config.get("cloud_sync_interval_minutes", 5)), 60))
            self.cloud_sync_periodic_id = self.root.after(interval * 60 * 1000, self._cloud_periodic_tick)

    def _cloud_periodic_tick(self) -> None:
        self.cloud_sync_periodic_id = None
        self._start_cloud_sync()
        self._schedule_cloud_sync_periodic()



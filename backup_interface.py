# -*- coding: utf-8 -*-
"""Feature-specific ISHApp behavior extracted from main.py."""
from __future__ import annotations

class BackupInterfaceMixin:
    def _backup_directory(self) -> Path:
        configured = str(self.config.get("backup_dir", "")).strip()
        return Path(configured).expanduser().resolve() if configured else default_backup_directory()

    def _migrate_legacy_backups_once(self, destination: Path) -> tuple[int, int]:
        with self.backup_migration_lock:
            if bool(self.config.get("backup_legacy_migrated", False)):
                return 0, 0
            copied, skipped = copy_verified_backups(DATA_DIR / "backups", destination)
            # Migrate verified historical archives to the cloud queue too; no archive is
            # pruned locally until its cloud upload has been confirmed.
            for candidate in sorted(destination.glob("ISH_backup_*.zip"), key=lambda item: item.name):
                if candidate.is_file() and not candidate.is_symlink():
                    try:
                        inspect_backup(candidate)
                    except Exception:
                        continue
                    self._queue_backup_upload(candidate)
                    if bool(self.config.get("backup_supabase_enabled", False)) and candidate.stat().st_size + 64 <= MAX_SUPABASE_FILE_BYTES:
                        self._queue_supabase_backup_upload(candidate)
            self.config["backup_legacy_migrated"] = True
            atomic_json_save(CONFIG_PATH, self.config)
            return copied, skipped

    def choose_backup_directory(self) -> None:
        current = self._backup_directory()
        initial = current if current.is_dir() else current.parent
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Выбери папку резервных копий (вне папки установки)",
            initialdir=str(initial if initial.exists() else Path.home()),
            mustexist=False,
        )
        if selected:
            self.backup_dir_var.set(str(Path(selected).expanduser().resolve()))
            self.save_backup_settings()

    def save_backup_settings(self) -> bool:
        try:
            retention = max(3, min(30, int(self.backup_retention_var.get())))
            cloud_retention = max(3, min(30, int(self.backup_cloud_retention_var.get())))
            supabase_retention = max(3, min(30, int(self.backup_supabase_retention_var.get())))
            backup_dir = Path(self.backup_dir_var.get().strip() or default_backup_directory()).expanduser().resolve()
            install_dir = (
                Path(sys.executable).resolve().parent
                if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parent
            )
            if backup_dir == install_dir or install_dir in backup_dir.parents:
                raise ValueError("Папку резервных копий нельзя размещать внутри папки установки программы. Выбери соседнюю папку на этом диске.")
            backup_dir.mkdir(parents=True, exist_ok=True)
            if not backup_dir.is_dir():
                raise OSError("Выбранный путь не является папкой.")
        except Exception as exc:
            messagebox.showerror("Резервное копирование", f"Не удалось сохранить папку копий или параметры: {exc}")
            return False
        self.config["auto_backup_enabled"] = bool(self.auto_backup_var.get())
        self.config["backup_retention_count"] = retention
        self.config["backup_dir"] = str(backup_dir)
        self.config["backup_cloud_enabled"] = bool(self.backup_cloud_enabled_var.get())
        self.config["backup_cloud_retention_count"] = cloud_retention
        self.config["backup_supabase_enabled"] = bool(self.backup_supabase_enabled_var.get())
        self.config["backup_supabase_retention_count"] = supabase_retention
        atomic_json_save(CONFIG_PATH, self.config)
        self.backup_status_var.set(
            f"Папка: {backup_dir} · локально: {retention} · Google Drive: "
            f"{'включён' if self.config['backup_cloud_enabled'] else 'выключен'} · Google Drive: {cloud_retention} · "
            f"Supabase: {'включён' if self.config['backup_supabase_enabled'] else 'выключен'} · {supabase_retention}"
        )
        return True

    def open_backup_folder(self) -> None:
        folder = self._backup_directory()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            self._open_local_folder(folder)
        except OSError as exc:
            messagebox.showerror("Папка резервных копий", str(exc))

    def _backup_queue_items(self) -> list[str]:
        values = load_json(BACKUP_UPLOAD_QUEUE_PATH, [])
        if not isinstance(values, list):
            return []
        safe = []
        for item in values:
            if not isinstance(item, str):
                continue
            path = Path(item).expanduser()
            if path.suffix.casefold() != ".zip" or not path.name.startswith("ISH_backup_"):
                continue
            try:
                value = str(path.resolve())
            except OSError:
                continue
            if value not in safe:
                safe.append(value)
        return safe

    def _save_backup_queue(self, values: list[str]) -> None:
        safe = []
        for item in values:
            if not isinstance(item, str):
                continue
            path = Path(item).expanduser()
            if path.suffix.casefold() != ".zip" or not path.name.startswith("ISH_backup_"):
                continue
            value = str(path.resolve())
            if value not in safe:
                safe.append(value)
        atomic_json_save(BACKUP_UPLOAD_QUEUE_PATH, safe)

    def _queue_backup_upload(self, archive_path: Path) -> None:
        pending = self._backup_queue_items()
        archive_value = str(archive_path.expanduser().resolve())
        if archive_value not in pending:
            pending.append(archive_value)
        self._save_backup_queue(pending)

    def _remove_backup_from_queue(self, filename: str) -> None:
        target = str(Path(filename).expanduser().resolve())
        self._save_backup_queue([item for item in self._backup_queue_items() if str(Path(item).resolve()) != target])

    def _backup_supabase_queue_items(self) -> list[str]:
        values = load_json(BACKUP_SUPABASE_UPLOAD_QUEUE_PATH, [])
        if not isinstance(values, list):
            return []
        safe: list[str] = []
        for item in values:
            if not isinstance(item, str):
                continue
            path = Path(item).expanduser()
            if path.suffix.casefold() != ".zip" or not path.name.startswith("ISH_backup_"):
                continue
            try:
                value = str(path.resolve())
            except OSError:
                continue
            if value not in safe:
                safe.append(value)
        return safe

    def _save_supabase_backup_queue(self, values: list[str]) -> None:
        safe: list[str] = []
        for item in values:
            if not isinstance(item, str):
                continue
            path = Path(item).expanduser()
            if path.suffix.casefold() != ".zip" or not path.name.startswith("ISH_backup_"):
                continue
            try:
                value = str(path.resolve())
            except OSError:
                continue
            if value not in safe:
                safe.append(value)
        atomic_json_save(BACKUP_SUPABASE_UPLOAD_QUEUE_PATH, safe)

    def _queue_supabase_backup_upload(self, archive_path: Path) -> None:
        pending = self._backup_supabase_queue_items()
        value = str(archive_path.expanduser().resolve())
        if value not in pending:
            pending.append(value)
        self._save_supabase_backup_queue(pending)

    @staticmethod
    def _supabase_backup_client(package: dict[str, Any]) -> tuple[SupabaseBackupClient, SupabaseCloudClient]:
        session = package.get("session", {}) if isinstance(package.get("session"), dict) else {}
        auth_client = SupabaseCloudClient(
            str(package.get("project_url", "")), str(package.get("publishable_key", "")), dict(session),
        )
        auth_client.ensure_fresh_session()
        storage_client = SupabaseBackupClient(
            str(package.get("project_url", "")), str(package.get("publishable_key", "")), dict(auth_client.session),
        )
        return storage_client, auth_client

    def _save_supabase_backup_session(self, package: dict[str, Any], auth_client: SupabaseCloudClient) -> None:
        updated = dict(package)
        updated["session"] = dict(auth_client.session)
        self._remember_cloud_package(updated)

    def _upload_supabase_backup_archive(self, archive_path: Path, package: dict[str, Any], retention: int) -> str:
        passphrase = str(package.get("e2e_passphrase", ""))
        if len(passphrase) < 10:
            raise SupabaseBackupError("В защищённой сессии Supabase не найден E2E-пароль резервных копий.")
        source = Path(archive_path).expanduser().resolve()
        if not source.is_file() or source.is_symlink():
            raise SupabaseBackupError("Локальный ZIP-архив для Supabase не найден.")
        encrypted_path = source.with_name(source.stem + ".supabase.mibak")
        try:
            encrypt_backup_file(source, encrypted_path, passphrase)
            encrypted_hash = backup_sha256_file(encrypted_path)
            encrypted_size = encrypted_path.stat().st_size
            if encrypted_size > MAX_SUPABASE_FILE_BYTES:
                raise SupabaseBackupError(
                    "Архив превышает лимит Supabase Free — 50 МБ на файл. "
                    "Полная копия остаётся локально и в Google Drive."
                )
            client, auth_client = self._supabase_backup_client(package)
            remote_name = f"{source.stem}_{encrypted_hash}.mibak"
            remote_path = f"{client.user_id}/{remote_name}"
            existing = next(
                (item for item in client.list_backup_files() if item.get("path") == remote_path),
                None,
            )
            if existing and int(existing.get("size", 0)) != encrypted_size:
                client.delete_backup_file(remote_path)
                existing = None
            if existing:
                # A matching file name is not enough: authenticate the bytes already in Storage.
                verify_existing = encrypted_path.with_name(encrypted_path.name + ".existing-check")
                try:
                    client.download_backup_file(remote_path, verify_existing)
                except SupabaseBackupError:
                    client.delete_backup_file(remote_path)
                    existing = None
                finally:
                    verify_existing.unlink(missing_ok=True)
            if not existing:
                client.prune_backup_files(max(1, int(retention) - 1))
                client.upload_backup_file(
                    encrypted_path, remote_name=remote_name, sha256=encrypted_hash,
                    app_version=APP_VERSION,
                    backup_kind=(source.stem.split("_")[2] if len(source.stem.split("_")) > 2 else "manual"),
                )
                listed = client.list_backup_files()
                existing = next(
                    (item for item in listed
                     if item.get("path") == remote_path and int(item.get("size", 0)) == encrypted_size
                     and item.get("sha256") == encrypted_hash),
                    None,
                )
                if not existing:
                    raise SupabaseBackupError("Supabase не подтвердил полную загрузку зашифрованной копии.")
                verify_path = encrypted_path.with_name(encrypted_path.name + ".verify")
                try:
                    verified = client.download_backup_file(remote_path, verify_path)
                    if str(verified.get("sha256", "")).lower() != encrypted_hash:
                        raise SupabaseBackupError("SHA-256 скачанного из Supabase архива не совпал.")
                finally:
                    verify_path.unlink(missing_ok=True)
            client.prune_backup_files(retention)
            self._save_supabase_backup_session(package, auth_client)
            return f"Зашифрованная копия подтверждена в Supabase: {remote_name}."
        finally:
            encrypted_path.unlink(missing_ok=True)

    def _upload_supabase_backup_queue(self, package: dict[str, Any], retention: int) -> tuple[int, int, str]:
        pending = self._backup_supabase_queue_items()
        uploaded, error_text = 0, ""
        remaining = list(pending)
        for filename in pending:
            archive = Path(filename).expanduser()
            if not archive.is_file() or archive.is_symlink():
                error_text = f"Локальный архив пока недоступен: {archive}. Очередь Supabase сохранена."
                break
            try:
                self._upload_supabase_backup_archive(archive, package, retention)
                remaining.remove(filename)
                self._save_supabase_backup_queue(remaining)
                uploaded += 1
            except Exception as exc:
                error_text = str(exc)
                break
        self._save_supabase_backup_queue(remaining)
        return uploaded, len(remaining), error_text

    @staticmethod
    def _backup_drive_client(package: dict[str, Any]) -> GoogleDriveVaultClient:
        if str(package.get("provider", "")) != "google_drive":
            raise GoogleDriveError("Резервные архивы поддерживаются через подключённый Google Drive.")
        session = package.get("session", {}) if isinstance(package.get("session"), dict) else {}
        return GoogleDriveVaultClient(
            str(package.get("client_id", "")),
            str(package.get("client_secret", "")),
            dict(session),
        )

    @staticmethod
    def _save_backup_drive_session(package: dict[str, Any], client: GoogleDriveVaultClient) -> None:
        updated = dict(package)
        updated["session"] = dict(client.session)
        save_protected_session(GOOGLE_DRIVE_SESSION_PATH, updated)

    def _upload_backup_archive(
        self,
        archive_path: Path,
        package: dict[str, Any],
        cloud_retention: int,
    ) -> str:
        passphrase = str(package.get("e2e_passphrase", ""))
        if len(passphrase) < 10:
            raise BackupEncryptionError("В защищённой сессии Google Drive не найден пароль E2E.")
        encrypted_path = archive_path.with_suffix(".mibak")
        if not encrypted_path.is_file():
            encrypt_backup_file(archive_path, encrypted_path, passphrase)
        encrypted_hash = backup_sha256_file(encrypted_path)
        client = self._backup_drive_client(package)

        # A previous upload may have reached Drive even if the client lost its response.
        # Check for an identical encrypted archive before trying to upload it again.
        remote_match = next(
            (
                item for item in client.list_backup_files()
                if item.get("sha256") == encrypted_hash
                and item.get("md5") == backup_file_md5(encrypted_path)
            ),
            None,
        )
        if remote_match:
            if int(remote_match.get("size", 0)) != encrypted_path.stat().st_size:
                raise GoogleDriveError("Размер уже загруженной резервной копии не совпадает. Локальный архив сохранён.")
            client.prune_backup_files(cloud_retention)
            self._save_backup_drive_session(package, client)
            encrypted_path.unlink(missing_ok=True)
            return f"Зашифрованная копия уже подтверждена в Google Drive: {remote_match.get('name', encrypted_path.name)}."

        limit_gb = max(1, min(int(self.config.get("google_drive_storage_limit_gb", 10) or 10), 10))
        encrypted_size = encrypted_path.stat().st_size
        usage = client.get_app_folder_usage() + client.get_backup_folder_usage()
        if usage + encrypted_size > limit_gb * 1024 * 1024 * 1024:
            client.prune_backup_files(cloud_retention)
            usage = client.get_app_folder_usage() + client.get_backup_folder_usage()
            if usage + encrypted_size > limit_gb * 1024 * 1024 * 1024:
                raise GoogleDriveError(
                    f"В папке ISH Cloud превышен мягкий лимит {limit_gb} ГБ. "
                    "Удалите старые архивы в Google Drive или увеличьте лимит в настройках."
                )

        parts = archive_path.stem.split("_")
        backup_kind = parts[2] if len(parts) > 2 and parts[0] in {"ISH", "MoyaIshka"} else "manual"
        client.upload_backup_file(
            encrypted_path,
            remote_name=encrypted_path.name,
            sha256=encrypted_hash,
            app_version=APP_VERSION,
            backup_kind=backup_kind,
        )
        local_md5 = backup_file_md5(encrypted_path)
        remote_match = next(
            (
                item for item in client.list_backup_files()
                if item.get("sha256") == encrypted_hash and item.get("md5") == local_md5
            ),
            None,
        )
        if not remote_match or int(remote_match.get("size", 0)) != encrypted_size:
            raise GoogleDriveError("Google Drive не подтвердил наличие полной копии после загрузки. Локальный архив сохранён.")
        client.prune_backup_files(cloud_retention)
        self._save_backup_drive_session(package, client)
        encrypted_path.unlink(missing_ok=True)
        return f"Зашифрованная копия подтверждена в Google Drive: {remote_match.get('name', encrypted_path.name)}."

    def _upload_backup_queue(
        self,
        backup_dir: Path,
        package: dict[str, Any],
        cloud_retention: int,
    ) -> tuple[int, int, str]:
        pending = self._backup_queue_items()
        uploaded = 0
        error_text = ""
        remaining = list(pending)
        for filename in pending:
            archive = Path(filename).expanduser()
            if not archive.is_file() or archive.is_symlink():
                error_text = f"Локальный архив пока недоступен: {archive}. Очередь сохранена."
                break
            try:
                self._upload_backup_archive(archive, package, cloud_retention)
                remaining.remove(filename)
                self._save_backup_queue(remaining)
                uploaded += 1
            except Exception as exc:
                error_text = str(exc)
                break
        self._save_backup_queue(remaining)
        return uploaded, len(remaining), error_text

    def _create_and_queue_backup(
        self,
        retention: int,
        backup_dir: Path,
        cloud_enabled: bool,
        package: dict[str, Any] | None,
        cloud_retention: int,
        supabase_enabled: bool = False,
        supabase_package: dict[str, Any] | None = None,
        supabase_retention: int = 7,
        *,
        automatic: bool,
    ) -> tuple[Path | None, str]:
        migration_note = ""
        try:
            migrated, skipped = self._migrate_legacy_backups_once(backup_dir)
            if migrated:
                migration_note = f"Перенесено старых резервных копий: {migrated}."
            if skipped:
                migration_note = (migration_note + " " if migration_note else "") + f"Повреждённых старых архивов пропущено: {skipped}."
        except Exception as exc:
            migration_note = f"Старые архивы пока не перенесены: {exc}"
        # Keep queued archives until every enabled cloud target has confirmed its copy.
        pending_count = len(self._backup_queue_items()) + len(self._backup_supabase_queue_items())
        effective_retention = max(retention, pending_count + 1)
        if automatic:
            archive = maybe_create_daily_backup(
                DATA_DIR, app_version=APP_VERSION, retention_count=effective_retention, backup_dir=backup_dir,
            )
        else:
            archive = create_backup(
                DATA_DIR, app_version=APP_VERSION, retention_count=effective_retention, backup_dir=backup_dir,
            )
        notes: list[str] = []
        if migration_note:
            notes.append(migration_note)
        if cloud_enabled:
            if archive is not None:
                self._queue_backup_upload(archive)
            if package:
                uploaded, pending, error_text = self._upload_backup_queue(backup_dir, package, cloud_retention)
                if error_text:
                    notes.append(f"Google Drive: ожидает повтора — {error_text}")
                elif uploaded:
                    notes.append(f"Google Drive: подтверждено копий {uploaded}; в очереди {pending}.")
                elif pending:
                    notes.append(f"Google Drive: ожидают отправки {pending}.")
                else:
                    notes.append("Google Drive: копии актуальны.")
            else:
                pending = len(self._backup_queue_items())
                if pending:
                    notes.append(f"Google Drive: ожидают подключения {pending} копий.")
                else:
                    notes.append("Google Drive не подключён; локальная копия сохранена.")
        if supabase_enabled:
            if archive is not None:
                try:
                    if archive.stat().st_size + 64 > MAX_SUPABASE_FILE_BYTES:
                        notes.append("Supabase: ZIP больше лимита 50 МБ; архив сохранён локально и в Google Drive.")
                    else:
                        self._queue_supabase_backup_upload(archive)
                except OSError as exc:
                    notes.append(f"Supabase: не удалось проверить локальный архив — {exc}")
            if supabase_package:
                uploaded, pending, error_text = self._upload_supabase_backup_queue(supabase_package, supabase_retention)
                if error_text:
                    notes.append(f"Supabase: ожидает повтора — {error_text}")
                elif uploaded:
                    notes.append(f"Supabase Storage: подтверждено копий {uploaded}; в очереди {pending}.")
                elif pending:
                    notes.append(f"Supabase Storage: ожидают отправки {pending}.")
                else:
                    notes.append("Supabase Storage: копии актуальны.")
            else:
                pending = len(self._backup_supabase_queue_items())
                if pending:
                    notes.append(f"Supabase: ожидают подключения {pending} копий.")
                else:
                    notes.append("Supabase Storage не подключён; локальная копия и Google Drive не затронуты.")
        return archive, " ".join(notes)

    def create_local_backup(self) -> None:
        if self.backup_working or self.backup_upload_working:
            self.backup_status_var.set("Операция с резервной копией уже выполняется.")
            return
        if not self.save_backup_settings():
            return
        self.backup_working = True
        self.backup_status_var.set("Создаю локальную копию и отправляю зашифрованный архив в облако…")
        threading.Thread(
            target=self._manual_backup_worker,
            args=(
                int(self.config.get("backup_retention_count", 7)),
                self._backup_directory(),
                bool(self.config.get("backup_cloud_enabled", True)),
                dict(self.google_drive_session) if self.google_drive_session_ready else None,
                int(self.config.get("backup_cloud_retention_count", 7)),
                bool(self.config.get("backup_supabase_enabled", False)),
                dict(self.cloud_session) if self.cloud_session_ready else None,
                int(self.config.get("backup_supabase_retention_count", 7)),
            ),
            daemon=True,
        ).start()

    def _manual_backup_worker(
        self,
        retention: int,
        backup_dir: Path,
        cloud_enabled: bool,
        package: dict[str, Any] | None,
        cloud_retention: int,
        supabase_enabled: bool = False,
        supabase_package: dict[str, Any] | None = None,
        supabase_retention: int = 7,
    ) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            archive, cloud_status = self._create_and_queue_backup(
                retention, backup_dir, cloud_enabled, package, cloud_retention,
                supabase_enabled, supabase_package, supabase_retention, automatic=False,
            )
            self.events.put(("backup_created", {
                "path": str(archive) if archive else "",
                "cloud_status": cloud_status,
            }))
        except Exception as exc:
            self.events.put(("backup_error", str(exc)))

    def _schedule_automatic_backup(self) -> None:
        if not self.root.winfo_exists():
            return
        if (
            bool(self.config.get("auto_backup_enabled", True))
            and not self.backup_working
            and not self.backup_upload_working
        ):
            self.backup_working = True
            threading.Thread(
                target=self._automatic_backup_worker,
                args=(
                    int(self.config.get("backup_retention_count", 7)),
                    self._backup_directory(),
                    bool(self.config.get("backup_cloud_enabled", True)),
                    dict(self.google_drive_session) if self.google_drive_session_ready else None,
                    int(self.config.get("backup_cloud_retention_count", 7)),
                    bool(self.config.get("backup_supabase_enabled", False)),
                    dict(self.cloud_session) if self.cloud_session_ready else None,
                    int(self.config.get("backup_supabase_retention_count", 7)),
                ),
                daemon=True,
            ).start()
        self.root.after(6 * 60 * 60 * 1000, self._schedule_automatic_backup)

    def _automatic_backup_worker(
        self,
        retention: int,
        backup_dir: Path,
        cloud_enabled: bool,
        package: dict[str, Any] | None,
        cloud_retention: int,
        supabase_enabled: bool = False,
        supabase_package: dict[str, Any] | None = None,
        supabase_retention: int = 7,
    ) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            archive, cloud_status = self._create_and_queue_backup(
                retention, backup_dir, cloud_enabled, package, cloud_retention,
                supabase_enabled, supabase_package, supabase_retention, automatic=True,
            )
            self.events.put(("backup_auto_result", {
                "path": str(archive) if archive else "",
                "cloud_status": cloud_status,
            }))
        except Exception as exc:
            self.events.put(("backup_error", str(exc)))

    def upload_pending_backups_now(self) -> None:
        if self.backup_upload_working or self.backup_working:
            self.backup_status_var.set("Другая операция с резервной копией уже выполняется.")
            return
        drive_pending = bool(self._backup_queue_items())
        supabase_pending = bool(self._backup_supabase_queue_items())
        drive_package = (
            dict(self.google_drive_session)
            if drive_pending and bool(self.config.get("backup_cloud_enabled", True)) and self.google_drive_session_ready
            else None
        )
        supabase_package = (
            dict(self.cloud_session)
            if supabase_pending and bool(self.config.get("backup_supabase_enabled", False)) and self.cloud_session_ready
            else None
        )
        if not drive_pending and not supabase_pending:
            self.backup_status_var.set("Нет копий, ожидающих отправки в облако.")
            return
        if not drive_package and not supabase_package:
            messagebox.showwarning(
                "Облачные резервные копии",
                "Подключи Google Drive или Supabase и включи соответствующее зеркало в настройках копирования.",
            )
            return
        self.backup_upload_working = True
        self.backup_status_var.set("Отправляю ожидающие резервные копии в доступные облака…")
        threading.Thread(
            target=self._retry_backup_upload_worker,
            args=(self._backup_directory(), drive_package, supabase_package,
                  int(self.config.get("backup_cloud_retention_count", 7)),
                  int(self.config.get("backup_supabase_retention_count", 7))),
            daemon=True,
        ).start()

    def _retry_backup_upload_worker(
        self, backup_dir: Path, drive_package: dict[str, Any] | None,
        supabase_package: dict[str, Any] | None, drive_retention: int, supabase_retention: int,
    ) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        results: dict[str, tuple[int, int, str]] = {}
        if drive_package:
            try:
                results["google_drive"] = self._upload_backup_queue(backup_dir, drive_package, drive_retention)
            except Exception as exc:
                results["google_drive"] = (0, len(self._backup_queue_items()), str(exc))
        if supabase_package:
            try:
                results["supabase"] = self._upload_supabase_backup_queue(supabase_package, supabase_retention)
            except Exception as exc:
                results["supabase"] = (0, len(self._backup_supabase_queue_items()), str(exc))
        self.events.put(("backup_upload_result", results))

    def _schedule_backup_upload_retry(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
            drive_pending = bool(self._backup_queue_items())
            supabase_pending = bool(self._backup_supabase_queue_items())
            drive_package = (
                dict(self.google_drive_session)
                if drive_pending and bool(self.config.get("backup_cloud_enabled", True)) and self.google_drive_session_ready
                else None
            )
            supabase_package = (
                dict(self.cloud_session)
                if supabase_pending and bool(self.config.get("backup_supabase_enabled", False)) and self.cloud_session_ready
                else None
            )
            if (drive_package or supabase_package) and not self.backup_working and not self.backup_upload_working:
                self.backup_upload_working = True
                threading.Thread(
                    target=self._retry_backup_upload_worker,
                    args=(self._backup_directory(), drive_package, supabase_package,
                          int(self.config.get("backup_cloud_retention_count", 7)),
                          int(self.config.get("backup_supabase_retention_count", 7))),
                    daemon=True,
                ).start()
        finally:
            try:
                if self.root.winfo_exists():
                    self.root.after(30 * 60 * 1000, self._schedule_backup_upload_retry)
            except tk.TclError:
                pass

    def restore_local_backup(self) -> None:
        if self.backup_working or self.backup_upload_working:
            messagebox.showwarning("Восстановление", "Дождись завершения текущей операции с резервной копией.")
            return
        if self.busy or self.research_busy or self.cloud_sync_busy or self.voice_busy or self.voice_download_busy:
            messagebox.showwarning(
                "Восстановление",
                "Сначала дождись завершения ответа ИИ, голосовой операции, исследования и облачной синхронизации.",
            )
            return
        folder = self._backup_directory()
        selected = filedialog.askopenfilename(
            title="Выбери резервную копию Моей ИИшки",
            initialdir=str(folder if folder.exists() else folder.parent),
            filetypes=[("Резервные копии ISH", "*.zip")],
        )
        if not selected:
            return
        if not messagebox.askyesno(
            "Восстановить резервную копию",
            "Текущая история, память, настройки, база знаний, навыки и плагины будут заменены данными из выбранного архива. "
            "Перед заменой программа создаст отдельную страховочную копию. Продолжить?",
        ):
            return
        if not self.save_backup_settings():
            return
        self.backup_working = True
        self.backup_status_var.set("Проверяю архив и подготавливаю безопасное восстановление…")
        if not self._begin_database_restore():
            return
        retention = int(self.config.get("backup_retention_count", 7))
        threading.Thread(
            target=self._restore_backup_worker,
            args=(selected, retention, self._backup_directory()),
            daemon=True,
        ).start()

    def _restore_backup_worker(self, archive_path: str, retention: int, backup_dir: Path) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            restored = restore_backup(
                archive_path, DATA_DIR, app_version=APP_VERSION,
                retention_count=retention, create_pre_restore_backup=True, backup_dir=backup_dir,
            )
            self.events.put(("backup_restore_complete", (True, str(restored.get("source", archive_path)))))
        except Exception as exc:
            self.events.put(("backup_restore_complete", (False, str(exc))))

    def restore_cloud_backup(self) -> None:
        if not self.google_drive_session_ready:
            messagebox.showwarning("Google Drive", "Для восстановления из облака сначала подключи Google Drive и пароль E2E.")
            return
        if self.backup_working or self.backup_upload_working:
            messagebox.showwarning("Восстановление", "Дождись завершения текущей операции с резервной копией.")
            return
        if self.busy or self.research_busy or self.cloud_sync_busy or self.voice_busy or self.voice_download_busy:
            messagebox.showwarning("Восстановление", "Сначала дождись завершения текущих задач ИИ.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Резервные копии Google Drive")
        dialog.transient(self.root)
        dialog.geometry("660x390")
        dialog.minsize(520, 300)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Выбери зашифрованную резервную копию. Перед восстановлением текущие данные будут сохранены.", wraplength=620).pack(anchor="w", pady=(0, 8))
        self.cloud_backup_listbox = tk.Listbox(frame, height=12, exportselection=False)
        self.cloud_backup_listbox.pack(fill="both", expand=True)
        self.cloud_backup_status_var = tk.StringVar(value="Получаю список резервных копий Google Drive…")
        ttk.Label(frame, textvariable=self.cloud_backup_status_var, wraplength=620).pack(anchor="w", pady=(8, 6))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="Обновить список", command=self._request_cloud_backup_list).pack(side="left")
        ttk.Button(actions, text="Восстановить выбранную", style="Accent.TButton", command=self._restore_selected_cloud_backup).pack(side="right")
        ttk.Button(actions, text="Закрыть", command=dialog.destroy).pack(side="right", padx=8)
        self.cloud_backup_dialog = dialog
        self.cloud_backup_items = []
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self._request_cloud_backup_list()

    def _request_cloud_backup_list(self) -> None:
        if not self.google_drive_session_ready:
            return
        package = dict(self.google_drive_session)
        threading.Thread(target=self._list_cloud_backups_worker, args=(package,), daemon=True).start()

    def _list_cloud_backups_worker(self, package: dict[str, Any]) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            client = self._backup_drive_client(package)
            items = client.list_backup_files()
            self._save_backup_drive_session(package, client)
            self.events.put(("backup_cloud_list", items))
        except Exception as exc:
            self.events.put(("backup_cloud_list_error", str(exc)))

    def _show_cloud_backup_items(self, items: list[dict[str, Any]]) -> None:
        try:
            if self.cloud_backup_dialog is None or not self.cloud_backup_dialog.winfo_exists() or self.cloud_backup_listbox is None:
                return
            self.cloud_backup_items = sorted(
                list(items or []),
                key=lambda item: str(item.get("modified_time", "")),
                reverse=True,
            )
            self.cloud_backup_listbox.delete(0, "end")
            for item in self.cloud_backup_items:
                when = str(item.get("modified_time", ""))
                try:
                    parsed = datetime.fromisoformat(when.replace("Z", "+00:00"))
                    when = parsed.astimezone().strftime("%d.%m.%Y %H:%M")
                except (ValueError, TypeError):
                    when = when or "дата неизвестна"
                size_mb = int(item.get("size", 0) or 0) / (1024 * 1024)
                self.cloud_backup_listbox.insert(
                    "end",
                    f"{item.get('name', 'Резервная копия')} · {when} · {size_mb:.1f} МБ",
                )
            if self.cloud_backup_status_var is not None:
                self.cloud_backup_status_var.set(
                    f"Найдено резервных копий: {len(self.cloud_backup_items)}. Архивы зашифрованы на этом ПК."
                    if self.cloud_backup_items else "В папке Google Drive пока нет резервных копий."
                )
        except tk.TclError:
            return

    def _restore_selected_cloud_backup(self) -> None:
        if self.cloud_backup_listbox is None:
            return
        if self.backup_working or self.backup_upload_working:
            messagebox.showwarning("Восстановление", "Дождись завершения текущей операции с резервной копией.")
            return
        selected = self.cloud_backup_listbox.curselection()
        if not selected or selected[0] >= len(self.cloud_backup_items):
            messagebox.showinfo("Google Drive", "Сначала выбери резервную копию.")
            return
        if self.busy or self.research_busy or self.cloud_sync_busy or self.voice_busy or self.voice_download_busy:
            messagebox.showwarning("Восстановление", "Сначала дождись завершения текущих задач ИИ.")
            return
        item = dict(self.cloud_backup_items[selected[0]])
        if not messagebox.askyesno(
            "Восстановить из Google Drive",
            f"Заменить текущую историю, память, настройки, базу знаний, навыки и плагины архивом «{item.get('name', '')}»? "
            "Перед этим будет создана страховочная копия текущих данных.",
        ):
            return
        if not self.save_backup_settings():
            return
        self.backup_working = True
        if not self._begin_database_restore():
            return
        backup_dir = self._backup_directory()
        retention = int(self.config.get("backup_retention_count", 7))
        package = dict(self.google_drive_session)
        try:
            if self.cloud_backup_dialog is not None:
                self.cloud_backup_dialog.destroy()
        except tk.TclError:
            pass
        self.cloud_backup_dialog = None
        threading.Thread(
            target=self._restore_cloud_backup_worker,
            args=(item, package, backup_dir, retention),
            daemon=True,
        ).start()

    def _restore_cloud_backup_worker(
        self,
        item: dict[str, Any],
        package: dict[str, Any],
        backup_dir: Path,
        retention: int,
    ) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        temp_root: Path | None = None
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            temp_root = Path(tempfile.mkdtemp(prefix=".cloud-restore-", dir=str(get_temp_directory("cloud_restore"))))
            safe_name = Path(str(item.get("name", "cloud-backup.mibak"))).name
            encrypted_path = temp_root / safe_name
            archive_path = temp_root / "restored_backup.zip"
            client = self._backup_drive_client(package)
            download_info = client.download_backup_file(str(item.get("id", "")), encrypted_path)
            expected_hash = str(item.get("sha256", "")).lower()
            if not expected_hash or str(download_info.get("sha256", "")).lower() != expected_hash:
                raise BackupEncryptionError("SHA-256 скачанной резервной копии не совпал с Google Drive. Восстановление отменено.")
            decrypt_backup_file(encrypted_path, archive_path, str(package.get("e2e_passphrase", "")))
            inspect_backup(archive_path)
            restored = restore_backup(
                archive_path, DATA_DIR, app_version=APP_VERSION,
                retention_count=retention, create_pre_restore_backup=True, backup_dir=backup_dir,
            )
            self._save_backup_drive_session(package, client)
            self.events.put((
                "backup_restore_complete",
                (True, f"Google Drive: {item.get('name', 'резервная копия')} · восстановлено файлов: {restored.get('files_restored', '0')}"),
            ))
        except Exception as exc:
            self.events.put(("backup_restore_complete", (False, str(exc))))
        finally:
            if temp_root is not None:
                shutil.rmtree(temp_root, ignore_errors=True)

    def restore_supabase_backup(self) -> None:
        if not self.cloud_session_ready:
            messagebox.showwarning("Supabase", "Сначала подключи резервное облако Supabase и пароль E2E.")
            return
        if self.backup_working or self.backup_upload_working:
            messagebox.showwarning("Восстановление", "Дождись завершения текущей операции с резервной копией.")
            return
        if self.busy or self.research_busy or self.cloud_sync_busy or self.voice_busy or self.voice_download_busy:
            messagebox.showwarning("Восстановление", "Сначала дождись завершения текущих задач ИИ.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Резервные копии Supabase Storage")
        dialog.transient(self.root)
        dialog.geometry("660x390")
        dialog.minsize(520, 300)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Выбери зашифрованный архив Supabase. Перед восстановлением текущие данные будут сохранены.", wraplength=620).pack(anchor="w", pady=(0, 8))
        self.supabase_backup_listbox = tk.Listbox(frame, height=12, exportselection=False)
        self.supabase_backup_listbox.pack(fill="both", expand=True)
        self.supabase_backup_status_var = tk.StringVar(value="Получаю список резервных копий Supabase…")
        ttk.Label(frame, textvariable=self.supabase_backup_status_var, wraplength=620).pack(anchor="w", pady=(8, 6))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="Обновить список", command=self._request_supabase_backup_list).pack(side="left")
        ttk.Button(actions, text="Восстановить выбранную", style="Accent.TButton", command=self._restore_selected_supabase_backup).pack(side="right")
        ttk.Button(actions, text="Закрыть", command=dialog.destroy).pack(side="right", padx=8)
        self.supabase_backup_dialog = dialog
        self.supabase_backup_items = []
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self._request_supabase_backup_list()

    def _request_supabase_backup_list(self) -> None:
        if self.cloud_session_ready:
            threading.Thread(target=self._list_supabase_backups_worker, args=(dict(self.cloud_session),), daemon=True).start()

    def _list_supabase_backups_worker(self, package: dict[str, Any]) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        try:
            client, auth_client = self._supabase_backup_client(package)
            items = client.list_backup_files()
            self._save_supabase_backup_session(package, auth_client)
            self.events.put(("backup_supabase_list", items))
        except Exception as exc:
            self.events.put(("backup_supabase_list_error", str(exc)))

    def _show_supabase_backup_items(self, items: list[dict[str, Any]]) -> None:
        try:
            if self.supabase_backup_dialog is None or not self.supabase_backup_dialog.winfo_exists() or self.supabase_backup_listbox is None:
                return
            self.supabase_backup_items = sorted(list(items or []), key=lambda item: str(item.get("created_at", "")), reverse=True)
            self.supabase_backup_listbox.delete(0, "end")
            for item in self.supabase_backup_items:
                when = str(item.get("created_at", ""))
                try:
                    when = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone().strftime("%d.%m.%Y %H:%M")
                except (ValueError, TypeError):
                    when = when or "дата неизвестна"
                size_mb = int(item.get("size", 0) or 0) / (1024 * 1024)
                self.supabase_backup_listbox.insert("end", f"{item.get('name', 'Резервная копия')} · {when} · {size_mb:.1f} МБ")
            if self.supabase_backup_status_var is not None:
                self.supabase_backup_status_var.set(
                    f"Найдено резервных копий: {len(self.supabase_backup_items)}. Архивы зашифрованы на этом ПК."
                    if self.supabase_backup_items else "В Supabase Storage пока нет резервных копий."
                )
        except tk.TclError:
            return

    def _restore_selected_supabase_backup(self) -> None:
        if self.supabase_backup_listbox is None:
            return
        if self.backup_working or self.backup_upload_working:
            messagebox.showwarning("Восстановление", "Дождись завершения текущей операции с резервной копией.")
            return
        selected = self.supabase_backup_listbox.curselection()
        if not selected or selected[0] >= len(self.supabase_backup_items):
            messagebox.showinfo("Supabase", "Сначала выбери резервную копию.")
            return
        if self.busy or self.research_busy or self.cloud_sync_busy or self.voice_busy or self.voice_download_busy:
            messagebox.showwarning("Восстановление", "Сначала дождись завершения текущих задач ИИ.")
            return
        item = dict(self.supabase_backup_items[selected[0]])
        if not messagebox.askyesno(
            "Восстановить из Supabase",
            f"Заменить текущую историю, память, настройки, базу знаний, навыки и плагины архивом «{item.get('name', '')}»? Перед этим будет создана страховочная копия.",
        ):
            return
        if not self.save_backup_settings():
            return
        self.backup_working = True
        if not self._begin_database_restore():
            return
        backup_dir = self._backup_directory()
        retention = int(self.config.get("backup_retention_count", 7))
        package = dict(self.cloud_session)
        try:
            if self.supabase_backup_dialog is not None:
                self.supabase_backup_dialog.destroy()
        except tk.TclError:
            pass
        self.supabase_backup_dialog = None
        threading.Thread(target=self._restore_supabase_backup_worker, args=(item, package, backup_dir, retention), daemon=True).start()

    def _restore_supabase_backup_worker(self, item: dict[str, Any], package: dict[str, Any], backup_dir: Path, retention: int) -> None:
        ResourceGovernor.set_current_thread_low_priority()
        temp_root: Path | None = None
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            temp_root = Path(tempfile.mkdtemp(prefix=".supabase-restore-", dir=str(get_temp_directory("supabase_restore"))))
            safe_name = Path(str(item.get("name", "supabase-backup.mibak"))).name
            encrypted_path, archive_path = temp_root / safe_name, temp_root / "restored_backup.zip"
            client, auth_client = self._supabase_backup_client(package)
            downloaded = client.download_backup_file(str(item.get("path", "")), encrypted_path)
            expected_hash = str(item.get("sha256", "")).lower()
            if not expected_hash or str(downloaded.get("sha256", "")).lower() != expected_hash:
                raise BackupEncryptionError("SHA-256 скачанной резервной копии Supabase не совпал. Восстановление отменено.")
            decrypt_backup_file(encrypted_path, archive_path, str(package.get("e2e_passphrase", "")))
            inspect_backup(archive_path)
            restored = restore_backup(
                archive_path, DATA_DIR, app_version=APP_VERSION,
                retention_count=retention, create_pre_restore_backup=True, backup_dir=backup_dir,
            )
            self._save_supabase_backup_session(package, auth_client)
            self.events.put(("backup_restore_complete", (
                True, f"Supabase Storage: {item.get('name', 'резервная копия')} · восстановлено файлов: {restored.get('files_restored', '0')}",
            )))
        except Exception as exc:
            self.events.put(("backup_restore_complete", (False, str(exc))))
        finally:
            if temp_root is not None:
                shutil.rmtree(temp_root, ignore_errors=True)

    def _begin_database_restore(self) -> bool:
        """Close SQLite safely and pause UI/background work during data replacement."""
        if self._database_restore_in_progress:
            return False
        self._database_restore_in_progress = True
        self._deferred_restore_events.clear()
        try:
            self.store.close()
        except Exception as exc:
            self._database_restore_in_progress = False
            self.backup_working = False
            messagebox.showerror(
                "Восстановление данных",
                "Не удалось безопасно закрыть базу данных. Восстановление отменено.\n\n" + str(exc),
            )
            return False

        # A previously scheduled sync must not read the database while the
        # restore worker replaces files. Its next attempt is scheduled later.
        if self.cloud_sync_after_id:
            try:
                self.root.after_cancel(self.cloud_sync_after_id)
            except Exception:
                pass
            self.cloud_sync_after_id = None

        # Prevent clicks that could call Store methods before the worker finishes.
        try:
            self.root.attributes("-disabled", True)
        except Exception:
            pass
        return True

    def _finish_database_restore(self, *, replay_events: bool) -> None:
        """Unlock the window and resume queued work after a new Store is ready."""
        self._database_restore_in_progress = False
        try:
            self.root.attributes("-disabled", False)
        except Exception:
            pass

        deferred = self._deferred_restore_events
        self._deferred_restore_events = []
        if replay_events:
            for event, payload in deferred:
                self.events.put((event, payload))

        if replay_events and self.cloud_sync_dirty:
            self.cloud_sync_dirty = False
            self._schedule_cloud_sync()

    def _reload_after_backup_restore(self) -> None:
        saved = load_json(CONFIG_PATH, {})
        self.config = dict(DEFAULT_CONFIG)
        if isinstance(saved, dict):
            self.config.update(saved)
        configure_temporary_storage(
            config=self.config,
            config_path=CONFIG_PATH,
            running_path=Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None,
            source_root=Path(__file__).resolve().parent,
        )
        self.api_key = unprotect_api_key(self.config)
        self.store = Store(DB_PATH)
        self.research_library = ResearchLibrary(DATA_DIR / "research_library.json", max_items=1000)
        self.plugin_manager = PluginManager(DATA_DIR, enabled_python=bool(self.config.get("plugins_enabled", False)))
        self.current_chat_id = self.store.ensure_conversation()
        self.cloud_session = load_protected_session(CLOUD_SESSION_PATH)
        self.google_drive_session = load_protected_session(GOOGLE_DRIVE_SESSION_PATH)
        self.cloud_session_ready = bool(
            self.cloud_session.get("session", {}).get("access_token")
            and self.cloud_session.get("e2e_passphrase")
        )
        self.google_drive_session_ready = self._is_google_drive_session_ready(self.google_drive_session)
        self._reload_settings_controls()
        if hasattr(self, "auto_backup_var"):
            self.auto_backup_var.set(bool(self.config.get("auto_backup_enabled", True)))
            self.backup_retention_var.set(str(self.config.get("backup_retention_count", 7)))
        self._refresh_chat_list()
        self._render_current_chat()
        self._refresh_memory_list()
        self._refresh_research_list()
        self._refresh_skill_list()



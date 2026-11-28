# -*- coding: utf-8 -*-
"""Application startup, updater handshakes and packaged runtime smoke tests."""
from __future__ import annotations

def migrate_staged_exe_on_first_launch() -> bool:
    """Install an EXE launched from update_staging into the chosen permanent folder.

    Older releases downloaded the new EXE into AppData and sometimes launched it
    directly. Do not try to overwrite the destination from this still-running EXE:
    Windows locks the image file. Instead, start the detached PowerShell installer,
    exit this process, and let the helper replace the target after both old instances
    have closed. The helper verifies SHA-256, embedded version, actual launch path,
    and the new process' startup receipt before reporting success.
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        running_exe = Path(sys.executable).resolve()
        if running_exe.parent.name.casefold() != "update_staging":
            return False

        saved_config = load_json(CONFIG_PATH, {})
        if not isinstance(saved_config, dict):
            saved_config = {}
        was_user_selected = bool(saved_config.get("install_dir_user_selected", False))
        configured_root = str(saved_config.get("install_root_dir", "")).strip()
        container_root = (
            Path(configured_root).expanduser().resolve()
            if configured_root
            else default_install_root(
                legacy_install_dir=saved_config.get("install_dir"),
                running_exe=(
                    None if running_exe.parent.name.casefold() == "update_staging"
                    else running_exe
                ),
            )
        )

        if not was_user_selected and not configured_root:
            chooser_root = tk.Tk()
            chooser_root.withdraw()
            try:
                selected = filedialog.askdirectory(
                    parent=chooser_root,
                    title="Выбери корневую папку контейнера (в ней будут App и Updates)",
                    initialdir=str(container_root),
                    mustexist=False,
                )
            finally:
                chooser_root.destroy()
            if not selected:
                # Keep the staged app usable; the user can set the target in Settings.
                return False
            container_root = Path(selected).expanduser().resolve()

        layout = ensure_install_layout(container_root)
        target_dir = ensure_install_dir_writable(layout["app"])
        ensure_install_dir_writable(layout["updates"])
        target_exe = target_dir / "ISH.exe"
        saved_config["install_root_dir"] = str(layout["root"])
        saved_config["updates_dir"] = str(layout["updates"])
        saved_config["install_dir"] = str(target_dir)
        saved_config["install_dir_user_selected"] = True
        atomic_json_save(CONFIG_PATH, saved_config)
        configure_temporary_storage(
            config=saved_config,
            config_path=CONFIG_PATH,
            running_path=running_exe,
        )

        # This process is the staged EXE. The helper waits for it to exit, then
        # atomically replaces target_exe and launches the verified new process.
        launch_windows_replacement(
            staged_path=running_exe,
            target_path=target_exe,
            parent_pid=os.getpid(),
            log_path=DATA_DIR / "update.log",
            expected_version=APP_VERSION,
            receipt_path=get_temp_directory("updates") / "update_confirmation.json",
        )
        return True
    except Exception as exc:
        try:
            messagebox.showerror(
                "Установка Моей ИИшки",
                f"Не удалось запустить безопасную установку из временной папки.\n\nПричина: {exc}\n\nСкачанный EXE сохранён здесь:\n{Path(sys.executable).resolve()}\n\nЖурнал установки:\n{DATA_DIR / 'update.log'}",
            )
        except Exception:
            pass
        return False



def confirm_update_startup(receipt_path: str, expected_version: str, expected_sha256: str, expected_target: str) -> tuple[bool, str]:
    """Confirm an updater launch only when version, executable path and hash match."""
    receipt = Path(receipt_path).expanduser().resolve()
    target = Path(expected_target).expanduser().resolve()
    try:
        actual_exe = Path(sys.executable).resolve()
        if not getattr(sys, "frozen", False):
            raise RuntimeError("Запустилась не автономная EXE-сборка.")
        if APP_VERSION != expected_version:
            raise RuntimeError(f"Запущена версия {APP_VERSION}, ожидалась {expected_version}.")
        if actual_exe != target:
            raise RuntimeError(f"Приложение запущено из {actual_exe}, ожидался путь {target}.")
        actual_hash = sha256_file(actual_exe)
        if actual_hash.lower() != expected_sha256.lower():
            raise RuntimeError("SHA-256 запущенного EXE не совпадает с загруженным файлом.")
        result = {
            "confirmed": True,
            "version": APP_VERSION,
            "target": str(actual_exe),
            "sha256": actual_hash.lower(),
            "message": "Новая версия успешно запущена и проверена.",
            "timestamp": datetime.now().astimezone().isoformat(),
        }
        atomic_json_save(receipt, result)
        return True, str(actual_exe)
    except Exception as exc:
        try:
            atomic_json_save(receipt, {
                "confirmed": False,
                "version": APP_VERSION,
                "target": str(Path(sys.executable).resolve()),
                "sha256": "",
                "message": str(exc),
                "timestamp": datetime.now().astimezone().isoformat(),
            })
        except Exception:
            pass
        return False, str(exc)


def _handle_update_confirmation_args(root: tk.Tk) -> None:
    """Process the private command line handshake passed by the Windows updater."""
    confirmation = None
    if len(sys.argv) >= 6 and sys.argv[1] == "--confirm-update":
        confirmation = tuple(sys.argv[2:6])
    elif all(os.environ.get(key) for key in (
        "MOYA_UPDATE_RECEIPT", "MOYA_UPDATE_VERSION",
        "MOYA_UPDATE_SHA256", "MOYA_UPDATE_TARGET",
    )):
        confirmation = (
            os.environ["MOYA_UPDATE_RECEIPT"],
            os.environ["MOYA_UPDATE_VERSION"],
            os.environ["MOYA_UPDATE_SHA256"],
            os.environ["MOYA_UPDATE_TARGET"],
        )
    if confirmation:
        receipt, version, expected_hash, target = confirmation

        def confirm() -> None:
            ok, detail = confirm_update_startup(receipt, version, expected_hash, target)
            if ok:
                messagebox.showinfo(
                    "Обновление подтверждено",
                    f"ISH версии {version} успешно установлена и запущена.\n\nФактический путь:\n{detail}",
                    parent=root,
                )

                # Search for legacy copies only after the updater has received a
                # valid startup receipt. A short delay lets its final backup cleanup
                # finish before this process inspects neighboring install folders.
                def start_old_version_cleanup() -> None:
                    def worker() -> None:
                        settings = load_json(CONFIG_PATH, DEFAULT_CONFIG)
                        if not isinstance(settings, dict) or not bool(
                            settings.get("auto_cleanup_old_versions", True)
                        ):
                            return
                        try:
                            result = cleanup_old_application_copies(
                                configured_install_dir=settings.get("install_dir") or Path(sys.executable).resolve().parent,
                                current_exe=Path(sys.executable).resolve(),
                                data_dir=DATA_DIR,
                            )
                            with (DATA_DIR / "update.log").open("a", encoding="utf-8") as log:
                                log.write(
                                    f"{datetime.now().astimezone().isoformat()}  "
                                    f"Автоочистка старых копий: найдено {result['found']}, "
                                    f"удалено {result['deleted']}, ошибок {len(result['errors'])}.\n"
                                )
                                for error in result["errors"][:10]:
                                    log.write(f"  {error}\n")
                        except Exception as exc:
                            try:
                                with (DATA_DIR / "update.log").open("a", encoding="utf-8") as log:
                                    log.write(f"{datetime.now().astimezone().isoformat()}  Ошибка автоочистки: {exc}\n")
                            except OSError:
                                pass

                    threading.Thread(target=worker, daemon=True).start()

                root.after(5000, start_old_version_cleanup)
            else:
                messagebox.showerror(
                    "Проверка обновления не пройдена",
                    f"Новая версия не прошла проверку. Установщик восстановит предыдущую версию.\n\nПричина: {detail}",
                    parent=root,
                )

        root.after(1200, confirm)
        return

    # If the helper rolled back, it leaves a failed receipt for the restored app.
    failure_receipt = get_temp_directory("updates") / "update_confirmation.json"
    previous = load_json(failure_receipt, {})
    if isinstance(previous, dict) and previous.get("confirmed") is False:
        try:
            failure_receipt.unlink(missing_ok=True)
        except OSError:
            pass
        reason = str(previous.get("message", "Неизвестная причина"))
        log_path = DATA_DIR / "update.log"

        def show_failure() -> None:
            messagebox.showwarning(
                "Обновление отменено — восстановлена предыдущая версия",
                f"Новая версия не прошла проверку. Предыдущая версия восстановлена.\n\nПричина: {reason}\n\nЖурнал установки:\n{log_path}",
                parent=root,
            )
        root.after(1200, show_failure)


def _packaged_import_self_test() -> int:
    """Fast, no-GUI smoke test for bundled native runtime and crypto imports."""
    try:
        # Do not let the CI runner's installed VC++ runtime mask missing files
        # in the one-file archive: verify the app-local runtime was extracted.
        if getattr(sys, "frozen", False):
            runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent / "_internal"))
            required_runtime = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
            missing_runtime = [name for name in required_runtime if not (runtime_root / name).is_file()]
            if missing_runtime:
                return 73

        # Force PyInstaller to include CFFI's native backend. Some runtime
        # dependencies load it dynamically, so static analysis can miss it.
        import cffi as _cffi  # noqa: F401
        import _cffi_backend  # noqa: F401

        salt = b"ISH-test-salt"
        key = _CryptoScrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(b"packaging-smoke-test")
        cipher = _CryptoAESGCM(key)
        nonce = b"\x01" * 12
        smoke_aad = f"{APP_VERSION}-smoke".encode("ascii")
        ciphertext = cipher.encrypt(nonce, b"ISH cryptography bundle OK", smoke_aad)
        plaintext = cipher.decrypt(nonce, ciphertext, smoke_aad)
        if plaintext != b"ISH cryptography bundle OK":
            return 71
        return 0
    except Exception:
        return 72


def main() -> None:
    try:
        startup_config = load_json(CONFIG_PATH, {})
        if not isinstance(startup_config, dict):
            startup_config = {}
        running_exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
        if not str(startup_config.get("install_root_dir", "")).strip():
            startup_config["install_root_dir"] = str(
                default_install_root(
                    legacy_install_dir=startup_config.get("install_dir"),
                    running_exe=running_exe,
                )
            )
        configure_temporary_storage(
            config=startup_config,
            config_path=CONFIG_PATH,
            running_path=running_exe,
            source_root=Path(__file__).resolve().parent,
        )
    except Exception as exc:
        try:
            messagebox.showerror(
                "Временная папка контейнера",
                f"Не удалось подготовить временную папку на выбранном диске. "
                f"Системная папка TEMP не будет использоваться.\\n\\n{exc}",
            )
        except Exception:
            pass
        return
    if os.name == "nt":
        try:
            # A stable AppUserModelID helps Windows associate the high-resolution
            # executable/window icon with the same taskbar application across updates.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MrNike227.ISH.Desktop")
        except Exception:
            pass
    if migrate_staged_exe_on_first_launch():
        return
    prepare_source_workspace()
    root = tk.Tk()
    ISHApp(root)
    _handle_update_confirmation_args(root)
    root.mainloop()

# -*- coding: utf-8 -*-
"""Provision and launch Windows Sandbox for untrusted self-improvement tests."""
from __future__ import annotations

# Standard library
import base64
import ctypes
import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from temporary_storage import get_temp_directory

FEATURE_NAME = "Containers-DisposableClientVM"
MINIMUM_BUILD = 18362
SUPPORTED_EDITIONS = {"Professional", "ProfessionalN", "Enterprise", "Education", "ProfessionalEducation", "ProfessionalEducationN"}
DEFAULT_TIMEOUT_SECONDS = 600
MAX_MEMORY_MB = 4096
MAX_INSTALL_RESULT_BYTES = 32 * 1024


def _powershell_path() -> Path:
    root = Path(os.environ.get("WINDIR", r"C:\Windows"))
    return root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def _host_details() -> dict[str, Any]:
    if os.name != "nt":
        return {"supported": False, "reason": "Windows Sandbox доступна только в Windows 10/11."}
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ) as key:
            edition = str(winreg.QueryValueEx(key, "EditionID")[0])
            build = int(winreg.QueryValueEx(key, "CurrentBuildNumber")[0])
    except (OSError, ValueError, TypeError) as exc:
        return {
            "supported": False,
            "reason": f"Не удалось подтвердить редакцию и сборку Windows: {exc}",
        }
    machine = platform.machine().casefold()
    if build < MINIMUM_BUILD:
        return {
            "supported": False, "edition": edition, "build": build,
            "reason": "Нужна Windows 10 версии 1903 или новее.",
        }
    allowed_architectures = {"amd64", "x86_64"} if build < 22621 else {"amd64", "x86_64", "arm64"}
    if machine not in allowed_architectures:
        return {
            "supported": False, "edition": edition, "build": build, "architecture": machine,
            "reason": "Эта архитектура Windows не поддерживается Windows Sandbox в установленной версии ОС.",
        }
    if edition and edition not in SUPPORTED_EDITIONS:
        return {
            "supported": False, "edition": edition, "build": build,
            "reason": "Windows Sandbox не поддерживается этой редакцией Windows.",
        }
    system_drive = os.environ.get("SystemDrive", "C:")
    system_root = Path(system_drive.rstrip("\\/") + "\\")
    try:
        disk_free_bytes = shutil.disk_usage(system_root).free
    except OSError:
        disk_free_bytes = 0
    disk_free_gb = round(disk_free_bytes / (1024 ** 3), 2)
    if disk_free_bytes < 1024 ** 3:
        return {
            "supported": False, "edition": edition, "build": build, "architecture": machine,
            "disk_free_gb": disk_free_gb,
            "reason": "Для Windows Sandbox нужен как минимум 1 ГБ свободного места на системном диске.",
        }
    return {
        "supported": True, "edition": edition, "build": build,
        "architecture": machine, "disk_free_gb": disk_free_gb, "reason": "",
    }



def _is_reparse_point(path: Path) -> bool:
    """Detect symlinks and Windows junction/reparse points without following them."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        # PowerShell creates the result only after UAC is accepted and the
        # optional-feature operation finishes. During polling, absence is
        # expected and must not be confused with a link/reparse point.
        return False
    except OSError:
        # If the path cannot be inspected for another reason, fail closed.
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    if attributes & reparse_flag:
        return True
    return path.is_symlink()


def _state_marker_path() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    directory = base / "MoyaIshka"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "windows_sandbox_state.json"


def record_windows_sandbox_install(result: dict[str, Any]) -> Path:
    """Persist only the verified Windows feature result and boot time, not arbitrary fields."""
    marker = {
        "schema": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "success": bool(result.get("success")),
        "state": str(result.get("state", "Unknown"))[:40],
        "restart_required": bool(result.get("restart_required")),
        "boot_time": str(result.get("boot_time", ""))[:64],
        "error": str(result.get("error", ""))[:1000],
    }
    path = _state_marker_path()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def _read_install_state() -> dict[str, Any] | None:
    try:
        path = _state_marker_path()
        if _is_reparse_point(path) or not path.is_file() or path.stat().st_size > MAX_INSTALL_RESULT_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("schema") == 1:
            return payload
    except (OSError, ValueError, TypeError):
        return None
    return None


def _parse_boot_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def get_windows_sandbox_status() -> dict[str, Any]:
    """Check readiness without elevation; the optional-feature cmdlets are admin-only."""
    details = _host_details()
    result: dict[str, Any] = {
        **details, "installed": False, "ready": False, "restart_required": False,
        "feature_state": "Unknown", "virtualization_ready": False,
        "memory_mb": 0, "cpu_cores": 0,
    }
    if not details.get("supported"):
        return result
    powershell = _powershell_path()
    if not powershell.is_file():
        result["reason"] = "Не найден системный Windows PowerShell."
        return result

    # CIM read-only queries are available to standard users. Administrative
    # optional-feature queries are deliberately excluded from this status path.
    command = (
        "$ErrorActionPreference='Stop'; "
        "$c=Get-CimInstance Win32_ComputerSystem; "
        "$p=Get-CimInstance Win32_Processor; "
        "$o=Get-CimInstance Win32_OperatingSystem; "
        "$boot=$o.LastBootUpTime.ToUniversalTime().ToString('o'); "
        "$virt=(($p | Where-Object {$_.VirtualizationFirmwareEnabled -ne $true}).Count -eq 0); "
        "$cores=[int](($p | Measure-Object -Property NumberOfCores -Sum).Sum); "
        "Write-Output ('MOYA_HYPERVISOR=' + [string]$c.HypervisorPresent); "
        "Write-Output ('MOYA_VIRT=' + [string]$virt); "
        "Write-Output ('MOYA_MEM_MB=' + [string][math]::Floor($c.TotalPhysicalMemory / 1MB)); "
        "Write-Output ('MOYA_CORES=' + [string]$cores); "
        "Write-Output ('MOYA_BOOT_TIME=' + $boot)"
    )
    try:
        completed = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            ),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["reason"] = f"Не удалось проверить компоненты Windows: {exc}"
        return result
    if completed.returncode != 0:
        result["reason"] = (
            "Не удалось проверить виртуализацию и гипервизор Windows. "
            + (completed.stderr or completed.stdout).strip()[-500:]
        )
        return result

    values: dict[str, str] = {}
    for line in (completed.stdout or "").splitlines():
        if line.startswith("MOYA_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip()
    try:
        result["memory_mb"] = int(values.get("MOYA_MEM_MB", "0") or 0)
        result["cpu_cores"] = int(values.get("MOYA_CORES", "0") or 0)
    except ValueError:
        result["reason"] = "Windows вернула некорректные данные о памяти или процессорах."
        return result

    result["virtualization_ready"] = values.get("MOYA_VIRT", "").casefold() == "true"
    result["boot_time"] = values.get("MOYA_BOOT_TIME", "")
    marker = _read_install_state()
    executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"
    executable_exists = executable.is_file()
    result["executable_path"] = str(executable)
    result["installed"] = executable_exists

    if marker:
        result["feature_state"] = str(marker.get("state", "Unknown"))
        result["restart_required"] = bool(marker.get("restart_required"))
        if result["restart_required"]:
            installed_boot = _parse_boot_time(str(marker.get("boot_time", "")))
            current_boot = _parse_boot_time(result["boot_time"])
            if installed_boot and current_boot and current_boot != installed_boot:
                result["restart_required"] = False
                result["feature_state"] = "EnabledAfterRestart"
                marker["restart_required"] = False
                marker["state"] = "EnabledAfterRestart"
                marker["boot_time"] = result["boot_time"]
                marker["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                record_windows_sandbox_install(marker)
    elif executable_exists:
        # Component may have been enabled manually in Windows Features.
        result["feature_state"] = "DetectedByExecutable"

    hypervisor_ready = values.get("MOYA_HYPERVISOR", "").casefold() == "true"
    result["ready"] = (
        executable_exists and not result["restart_required"]
        and result["virtualization_ready"] and hypervisor_ready
        and result["memory_mb"] >= 4096 and result["cpu_cores"] >= 2
        and float(details.get("disk_free_gb", 0) or 0) >= 1
    )
    if result["restart_required"]:
        result["reason"] = "Компонент включён, но Windows ещё не перезагружалась после установки."
    elif not executable_exists:
        result["reason"] = "Windows Sandbox не установлена. Нажми «Установить Windows Sandbox»."
    elif not result["virtualization_ready"]:
        result["reason"] = "Включи Intel VT-x / AMD-V (виртуализацию) в BIOS/UEFI и перезагрузи ПК."
    elif result["memory_mb"] < 4096 or result.get("cpu_cores", 0) < 2:
        result["reason"] = "Для Windows Sandbox нужно не менее 4 ГБ ОЗУ и двух физических ядер процессора."
    elif not hypervisor_ready:
        result["reason"] = "Гипервизор Windows не запущен. Проверь виртуализацию и перезагрузи ПК."
    else:
        result["reason"] = "Windows Sandbox прошла предварительные проверки. Фактический запуск проверяется при тестировании."
    return result


def request_windows_sandbox_install() -> Path:
    """Enable the Windows optional feature through a visible, explicit UAC prompt."""
    details = _host_details()
    if not details.get("supported"):
        raise RuntimeError(str(details.get("reason") or "Этот компьютер не поддерживает Windows Sandbox."))
    powershell = _powershell_path()
    if not powershell.is_file():
        raise RuntimeError("Не найден Windows PowerShell.")

    work = Path(tempfile.mkdtemp(prefix="moya_sandbox_setup_", dir=str(get_temp_directory("sandbox_setup"))))
    result_path = work / "install_result.json"
    result_literal = str(result_path).replace("'", "''")
    # Use an inline encoded command rather than elevating a script from the
    # user-writable temporary folder (which would permit a script-swap race).
    script = f"""$ErrorActionPreference = 'Stop'
$resultPath = '{result_literal}'
try {{
    $feature = Get-WindowsOptionalFeature -Online -FeatureName '{FEATURE_NAME}'
    $restartNeeded = $false
    if ([string]$feature.State -ne 'Enabled') {{
        $enableResult = Enable-WindowsOptionalFeature -Online -FeatureName '{FEATURE_NAME}' -All -NoRestart
        $restartNeeded = [bool]$enableResult.RestartNeeded
    }}
    $current = Get-WindowsOptionalFeature -Online -FeatureName '{FEATURE_NAME}'
    if ([string]$current.State -eq 'EnablePending') {{ $restartNeeded = $true }}
    $osInfo = Get-CimInstance Win32_OperatingSystem
    $bootTime = $osInfo.LastBootUpTime.ToUniversalTime().ToString('o')
    $data = [ordered]@{{success=([string]$current.State -in @('Enabled','EnablePending')); state=[string]$current.State; restart_required=$restartNeeded; boot_time=$bootTime; error=''}}
}} catch {{
    $data = [ordered]@{{success=$false; state='Error'; restart_required=$false; boot_time=''; error=$_.Exception.Message}}
}}
$data | ConvertTo-Json -Compress | Set-Content -LiteralPath $resultPath -Encoding UTF8
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    parameters = f'-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}'
    try:
        shell = ctypes.windll.shell32.ShellExecuteW
        shell.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int,
        ]
        shell.restype = ctypes.c_void_p
        code = shell(None, "runas", str(powershell), parameters, str(work), 1)
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError(f"Не удалось запросить права администратора: {exc}") from exc
    if int(code or 0) <= 32:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError("Установка отменена или Windows не смогла открыть запрос прав администратора.")
    return result_path


def wait_for_install_result(result_path: str | Path, timeout_seconds: int = 900) -> dict[str, Any]:
    path = Path(result_path)
    deadline = time.monotonic() + max(30, min(int(timeout_seconds), 1800))
    while time.monotonic() < deadline:
        if _is_reparse_point(path):
            raise RuntimeError("Результат установки Windows Sandbox является ссылкой или reparse point.")
        if path.is_file():
            try:
                if path.stat().st_size > MAX_INSTALL_RESULT_BYTES:
                    raise RuntimeError("Результат установки Windows Sandbox превышает безопасный размер.")
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
                    raise RuntimeError("Windows вернула результат установки в неизвестном формате.")
                # A completed UAC request no longer needs its result JSON. Keep
                # timed-out folders for diagnosis, but remove successful/failed
                # completed work folders from the container Temp tree.
                try:
                    setup_root = get_temp_directory("sandbox_setup").resolve()
                    if path.parent.parent.resolve() == setup_root and path.parent.name.startswith("moya_sandbox_setup_"):
                        shutil.rmtree(path.parent, ignore_errors=True)
                except OSError:
                    pass
                return payload
            except (OSError, ValueError):
                pass
        time.sleep(1)
    raise TimeoutError("Не получен результат установки Windows Sandbox. Проверь окно UAC/PowerShell и повтори проверку.")


def create_sandbox_config(
    readonly_host_dir: str | Path,
    writable_host_dir: str | Path,
    config_path: str | Path,
    *,
    memory_mb: int = MAX_MEMORY_MB,
    command: str = r"powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File C:\MoyaTest\ReadOnly\run_tests.ps1",
) -> Path:
    """Create a hardened WSB file: no network/clipboard/devices, read-only project, isolated output."""
    readonly = Path(readonly_host_dir).resolve()
    writable = Path(writable_host_dir).resolve()
    target = Path(config_path).resolve()
    if not readonly.is_dir() or not writable.is_dir():
        raise ValueError("Папки тестового пакета и результатов должны существовать.")
    if readonly == writable or readonly in writable.parents or writable in readonly.parents:
        raise ValueError("Папка результатов должна быть отдельной от тестового пакета.")
    memory = max(2048, min(int(memory_mb), 8192))
    xml = f"""<Configuration>
  <VGpu>Disable</VGpu>
  <ProtectedClient>Enable</ProtectedClient>
  <Networking>Disable</Networking>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <PrinterRedirection>Disable</PrinterRedirection>
  <MemoryInMB>{memory}</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{escape(str(readonly))}</HostFolder>
      <SandboxFolder>C:\\MoyaTest\\ReadOnly</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{escape(str(writable))}</HostFolder>
      <SandboxFolder>C:\\MoyaTest\\Result</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>{escape(command)}</Command>
  </LogonCommand>
</Configuration>
"""
    target.write_text(xml, encoding="utf-8")
    return target


def launch_windows_sandbox(config_path: str | Path) -> subprocess.Popen:
    """Launch a WSB configuration only after the OS feature is fully ready."""
    status = get_windows_sandbox_status()
    if not status.get("ready"):
        raise RuntimeError(str(status.get("reason") or "Windows Sandbox не готова."))
    executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"
    config = Path(config_path).resolve()
    if config.suffix.casefold() != ".wsb" or not config.is_file():
        raise ValueError("Не найден корректный файл конфигурации Windows Sandbox.")
    return subprocess.Popen(
        [str(executable), str(config)],
        cwd=str(config.parent),
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def wait_for_sandbox_completion(
    result_dir: str | Path,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    sandbox_process: subprocess.Popen | None = None,
    max_result_bytes: int = 16 * 1024 * 1024,
) -> dict[str, Any]:
    """Wait for guest completion while bounding untrusted files written to the host share."""
    directory = Path(result_dir).resolve()
    completion = directory / "complete.json"
    deadline = time.monotonic() + max(60, min(int(timeout_seconds) + 120, 900))
    while time.monotonic() < deadline:
        total_bytes = 0
        try:
            # The guest is expected to create exactly these three small JSON files.
            # Reject directories, links, ADS-like extras and all other output names.
            allowed_names = {"runner_result.json", "host_report.json", "complete.json"}
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name not in allowed_names:
                        if sandbox_process is not None and sandbox_process.poll() is None:
                            sandbox_process.kill()
                        raise RuntimeError("Sandbox создала неожиданный объект в папке результатов; отчёт отклонён.")
                    item = Path(entry.path)
                    info = entry.stat(follow_symlinks=False)
                    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                    if item.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & reparse_flag) or not stat.S_ISREG(info.st_mode):
                        if sandbox_process is not None and sandbox_process.poll() is None:
                            sandbox_process.kill()
                        raise RuntimeError("Sandbox создала ссылку или не-файл в папке результатов; отчёт отклонён.")
                    total_bytes += int(info.st_size)
                    if total_bytes > max_result_bytes:
                        if sandbox_process is not None and sandbox_process.poll() is None:
                            sandbox_process.kill()
                        raise RuntimeError("Sandbox превысила лимит 16 МБ для отчётов; процесс остановлен.")
        except OSError as exc:
            if sandbox_process is not None and sandbox_process.poll() is None:
                sandbox_process.kill()
            raise RuntimeError(f"Не удалось проверить результаты Windows Sandbox: {exc}") from exc
        process_exited = sandbox_process is None or sandbox_process.poll() is not None
        if process_exited and completion.is_file() and not _is_reparse_point(completion):
            try:
                if completion.stat().st_size <= 16 * 1024:
                    data = json.loads(completion.read_text(encoding="utf-8-sig"))
                    if (
                        isinstance(data, dict)
                        and data.get("schema") == 1
                        and data.get("completed") is True
                        and data.get("sandboxed") is True
                        and isinstance(data.get("guest_exit_code"), int)
                        and not isinstance(data.get("guest_exit_code"), bool)
                    ):
                        return data
            except (OSError, ValueError):
                pass
        time.sleep(1)
    if sandbox_process is not None and sandbox_process.poll() is None:
        sandbox_process.kill()
    raise TimeoutError("Windows Sandbox не вернула результат за отведённое время. Изменения не применены.")

# -*- coding: utf-8 -*-
"""Validate proposal packages and test them only inside Windows Sandbox."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from improvement_delivery import _is_test_module_path, _safe_relative_path, _write_text_atomic
from self_improvement import split_multi_file_unified_diff, apply_multi_file_unified_diff
from temporary_storage import get_temp_directory
from windows_sandbox import _is_reparse_point


class ProposalTestError(RuntimeError):
    """Proposal integrity or test execution error."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized_text_sha256(data: bytes) -> str:
    text = data.decode("utf-8")
    return _sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def _path_has_reparse_component(path: Path) -> bool:
    """Check the supplied path and each existing parent without resolving links first."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if os.path.lexists(current) and _is_reparse_point(current):
            return True
    return False


def _ignore_sandbox_copy(directory: str, names: list[str]) -> set[str]:
    """Omit secrets, user state, links and bulky local artifacts from the guest copy."""
    ignored_dirs = {
        ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", "build", "dist", "node_modules", "Updates",
        "ISH_Backups", "backups",
    }
    ignored_files = {
        ".env", ".env.local", ".env.production", "config.json", "credentials.json",
        "secrets.json", "cloud_session.dat", "google_drive_session.dat",
        "assistant.db", "memory.db", "id_rsa", "id_ed25519",
    }
    base = Path(directory)
    result: set[str] = set()
    for name in names:
        candidate = base / name
        lowered = name.casefold()
        if _is_reparse_point(candidate):
            result.add(name)
        elif candidate.is_dir() and lowered in ignored_dirs:
            result.add(name)
        elif candidate.is_file() and (
            lowered in ignored_files
            or lowered.startswith(".env.")
            or lowered.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".pfx", ".p12", ".key", ".log"))
        ):
            result.add(name)
    return result


def _prepare_guest_runner(readonly_root: Path) -> Path:
    """Copy only the installed onedir EXE and its private runtime into the read-only payload."""
    if not getattr(sys, "frozen", False):
        raise ProposalTestError(
            "Для реального тестирования нужна установленная сборка ISH (EXE onedir). "
            "Запуск тестового кода на основном Python запрещён."
        )
    executable = Path(sys.executable).resolve()
    internal = executable.parent / "_internal"
    if executable.name.casefold() != "ish.exe" or not executable.is_file() or not internal.is_dir():
        raise ProposalTestError("Для тестирования требуется полная сборка ISH.exe с каталогом _internal.")
    runner = readonly_root / "Runner"
    runner.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, runner / executable.name)
    shutil.copytree(internal, runner / "_internal")
    return runner / executable.name


def _guest_script(timeout_seconds: int) -> str:
    timeout_ms = max(30_000, min(int(timeout_seconds), 600)) * 1000
    return rf"""$ErrorActionPreference = 'Stop'
$root = 'C:\MoyaTest\ReadOnly'
$result = 'C:\MoyaTest\Result'
$project = Join-Path $root 'Project'
$runner = Join-Path $root 'Runner\ISH.exe'
$runnerResult = Join-Path $result 'runner_result.json'
$hostReport = Join-Path $result 'host_report.json'
$completion = Join-Path $result 'complete.json'
$exitCode = 1
$testData = $null
$errorText = ''
try {{
    New-Item -ItemType Directory -Force -Path 'C:\MoyaTemp' | Out-Null
    New-Item -ItemType Directory -Force -Path 'C:\MoyaTemp\AppData','C:\MoyaTemp\LocalAppData' | Out-Null
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $runner
    $psi.Arguments = '--run-proposal-tests "C:\MoyaTest\ReadOnly\Project" "C:\MoyaTest\Result\runner_result.json"'
    $psi.WorkingDirectory = $project
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables['TEMP'] = 'C:\MoyaTemp'
    $psi.EnvironmentVariables['TMP'] = 'C:\MoyaTemp'
    $psi.EnvironmentVariables['APPDATA'] = 'C:\MoyaTemp\AppData'
    $psi.EnvironmentVariables['LOCALAPPDATA'] = 'C:\MoyaTemp\LocalAppData'
    $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $psi.EnvironmentVariables['MOYA_WINDOWS_SANDBOX'] = '1'
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) {{ throw 'Не удалось запустить тестовый EXE в песочнице.' }}
    try {{ $process.PriorityClass = 'BelowNormal' }} catch {{ }}
    if (-not $process.WaitForExit({timeout_ms})) {{
        try {{ $process.Kill() }} catch {{}}
        $exitCode = 124
        $errorText = 'Превышено время выполнения тестов внутри Windows Sandbox.'
    }} else {{
        $exitCode = $process.ExitCode
    }}
    if (Test-Path -LiteralPath $runnerResult) {{
        $runnerInfo = Get-Item -LiteralPath $runnerResult -Force
        if (($runnerInfo.Length -le 1048576) -and -not ($runnerInfo.Attributes -band [IO.FileAttributes]::ReparsePoint)) {{
            $testData = Get-Content -LiteralPath $runnerResult -Raw | ConvertFrom-Json
        }} else {{
            $errorText = 'Отчёт тестового EXE слишком велик или является ссылкой.'
        }}
    }} elseif (-not $errorText) {{
        $errorText = 'Тестовый EXE не создал отчёт.'
    }}
}} catch {{
    $errorText = $_.Exception.Message
}}
$passed = ($exitCode -eq 0) -and ($null -ne $testData) -and [bool]$testData.passed -and ([int]$testData.tests_run -gt 0)
$report = [ordered]@{{
    schema = 1
    sandboxed = $true
    networking = 'disabled'
    project_mapping = 'read_only'
    writable_host_mapping = 'dedicated_results_only'
    passed = $passed
    tests_run = if ($null -ne $testData) {{ [int]$testData.tests_run }} else {{ 0 }}
    failures = if ($null -ne $testData) {{ [int]$testData.failures }} else {{ 0 }}
    errors = if ($null -ne $testData) {{ [int]$testData.errors }} else {{ 0 }}
    tests_exit_code = $exitCode
    stdout = if ($null -ne $testData) {{ [string]$testData.stdout }} else {{ '' }}
    stderr = if ($null -ne $testData) {{ [string]$testData.stderr }} else {{ '' }}
    error = $errorText
}}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $hostReport -Encoding UTF8
[ordered]@{{schema=1; completed=$true; sandboxed=$true; guest_exit_code=$exitCode; timestamp=[DateTime]::UtcNow.ToString('o')}} |
    ConvertTo-Json -Compress | Set-Content -LiteralPath $completion -Encoding UTF8
Start-Sleep -Seconds 3
& "$env:WINDIR\System32\shutdown.exe" /s /t 0 /f
"""


def _run_windows_sandbox(
    readonly_root: Path,
    writable_root: Path,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Launch the real Windows Sandbox. There is deliberately no local fallback."""
    from windows_sandbox import (
        create_sandbox_config,
        get_windows_sandbox_status,
        launch_windows_sandbox,
        wait_for_sandbox_completion,
    )

    status = get_windows_sandbox_status()
    if not status.get("ready"):
        raise ProposalTestError(
            "Тестирование заблокировано: Windows Sandbox не готова. "
            + str(status.get("reason") or "Установи и включи Windows Sandbox.")
        )
    runner = _prepare_guest_runner(readonly_root)
    (readonly_root / "run_tests.ps1").write_text(_guest_script(timeout_seconds), encoding="utf-8")
    config = readonly_root.parent / "ISH_Tests.wsb"
    create_sandbox_config(readonly_root, writable_root, config, memory_mb=4096)
    try:
        sandbox_process = launch_windows_sandbox(config)
        completion = wait_for_sandbox_completion(
            writable_root, timeout_seconds=timeout_seconds, sandbox_process=sandbox_process,
        )
    except TimeoutError as exc:
        raise ProposalTestError(
            f"{exc} Временный пакет оставлен для диагностики: {readonly_root.parent}"
        ) from exc
    report_path = writable_root / "host_report.json"
    if _is_reparse_point(report_path) or not report_path.is_file() or report_path.stat().st_size > 1024 * 1024:
        raise ProposalTestError("Итоговый отчёт отсутствует, слишком велик или является ссылкой.")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProposalTestError(f"Отчёт песочницы повреждён: {exc}") from exc
    if (
        not isinstance(report, dict)
        or report.get("schema") != 1
        or report.get("sandboxed") is not True
    ):
        raise ProposalTestError("Отчёт не подтвердил выполнение внутри Windows Sandbox.")
    if (
        completion.get("sandboxed") is not True
        or completion.get("guest_exit_code") != report.get("tests_exit_code")
    ):
        raise ProposalTestError(
            "Квитанция завершения Windows Sandbox не совпадает с кодом возврата тестового процесса."
        )
    report["guest_completion"] = completion
    report["runner_path"] = str(runner)
    return report


def test_change_bundle(
    bundle_dir: str | Path,
    source_root: str | Path,
    *,
    timeout_seconds: int = 600,
    sandbox_executor: Callable[[Path, Path, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify all files and their combined diff, then test the full proposal in Windows Sandbox.

    New Python test files are supported. Production callers never execute generated code on the host.
    """
    bundle_input = Path(bundle_dir).expanduser()
    source_input = Path(source_root).expanduser()
    if _path_has_reparse_component(bundle_input) or _path_has_reparse_component(source_input):
        raise ProposalTestError("Путь к предложению или исходникам содержит ссылку/reparse point.")
    try:
        bundle = bundle_input.resolve(strict=True)
        source = source_input.resolve(strict=True)
    except OSError as exc:
        raise ProposalTestError(f"Не удалось открыть папку предложения или исходников: {exc}") from exc
    if not bundle.is_dir() or not source.is_dir():
        raise ProposalTestError("Не найдена папка предложения или исходников.")

    manifest_path = bundle / "manifest.json"
    if _is_reparse_point(manifest_path) or not manifest_path.is_file() or manifest_path.stat().st_size > 128 * 1024:
        raise ProposalTestError("Манифест предложения отсутствует, слишком велик или является ссылкой.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProposalTestError(f"Манифест предложения повреждён: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ProposalTestError("Манифест предложения имеет неверный формат.")
    entries = manifest.get("files")
    if (
        manifest.get("schema") != 1
        or not isinstance(entries, list)
        or not 1 <= len(entries) <= 10
    ):
        raise ProposalTestError("Пакет должен содержать от 1 до 10 изменённых Python-файлов.")

    patch_meta = manifest.get("patch")
    if not isinstance(patch_meta, dict) or patch_meta.get("path") != "changes.patch":
        raise ProposalTestError("В манифесте отсутствует корректная ссылка на diff.")
    patch_path = bundle / "changes.patch"
    if _is_reparse_point(patch_path) or not patch_path.is_file():
        raise ProposalTestError("Файл diff предложения не найден или является ссылкой.")
    patch_resolved = patch_path.resolve()
    if bundle not in patch_resolved.parents or patch_path.stat().st_size > 2 * 1024 * 1024:
        raise ProposalTestError("Diff вышел за пределы пакета или превышает 2 МБ.")
    patch_bytes = patch_path.read_bytes()
    if len(patch_bytes) != patch_meta.get("size") or _sha256(patch_bytes) != patch_meta.get("sha256"):
        raise ProposalTestError("Контрольная сумма diff не совпадает.")
    try:
        patch_text = patch_bytes.decode("utf-8")
        file_patches = split_multi_file_unified_diff(patch_text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProposalTestError(f"Многофайловый diff повреждён: {exc}") from exc

    checked: list[tuple[Any, bytes, bytes, str | None]] = []
    total = 0
    sources: dict[str, str | None] = {}
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProposalTestError("Запись файла в манифесте имеет неверный формат.")
        try:
            relative = _safe_relative_path(entry.get("path", ""))
        except Exception as exc:
            raise ProposalTestError(str(exc)) from exc
        relative_name = relative.as_posix()
        if relative_name in seen:
            raise ProposalTestError(f"Файл повторяется в манифесте: {relative_name}.")
        seen.add(relative_name)

        source_candidate = source / Path(*relative.parts)
        bundle_candidate = bundle / "files" / Path(*relative.parts)
        # Reject reparse points in every existing component, including parent junctions.
        for candidate, boundary in ((source_candidate, source), (bundle_candidate, bundle / "files")):
            current = candidate
            while current != boundary.parent:
                if os.path.lexists(current) and _is_reparse_point(current):
                    raise ProposalTestError(f"Путь содержит символическую ссылку или junction: {relative_name}.")
                current = current.parent
        source_exists = os.path.lexists(source_candidate)
        candidate_resolved = bundle_candidate.resolve()
        if source not in source_candidate.resolve(strict=False).parents:
            raise ProposalTestError(f"Исходный путь выходит за пределы проекта: {relative_name}.")
        if bundle not in candidate_resolved.parents:
            raise ProposalTestError(f"Файл предложения выходит за пределы пакета: {relative_name}.")
        if not bundle_candidate.is_file():
            raise ProposalTestError(f"Не найден файл предложения: {relative_name}.")

        base_hash = entry.get("base_sha256")
        if base_hash == "absent":
            if source_exists:
                raise ProposalTestError(
                    f"Новый файл {relative_name} уже существует в исходниках. Создай предложение заново."
                )
            old = b""
            old_text: str | None = None
        else:
            if not source_exists or not source_candidate.is_file():
                raise ProposalTestError(f"Исходный файл {relative_name} отсутствует.")
            old = source_candidate.read_bytes()
            try:
                source_hash = _normalized_text_sha256(old)
            except UnicodeDecodeError as exc:
                raise ProposalTestError(f"Исходник {relative_name} не является UTF-8.") from exc
            if source_hash != base_hash:
                raise ProposalTestError(f"Исходник {relative_name} уже изменился. Создай предложение заново.")
            try:
                old_text = old.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProposalTestError(f"Исходник {relative_name} не является UTF-8.") from exc

        new = bundle_candidate.read_bytes()
        if base_hash != "absent" and old == new:
            raise ProposalTestError(f"Файл {relative_name} указан в пакете, но его содержимое не изменилось.")
        total += len(old) + len(new)
        if len(new) > 2 * 1024 * 1024 or total > 8 * 1024 * 1024:
            raise ProposalTestError("Размер файлов пакета превышает безопасный лимит.")
        if _sha256(new) != entry.get("sha256") or len(new) != entry.get("size"):
            raise ProposalTestError(f"Размер или SHA-256 изменённого файла не совпадает: {relative_name}.")
        try:
            updated_text = new.decode("utf-8")
            compile(updated_text, relative_name, "exec")
        except Exception as exc:
            raise ProposalTestError(f"Файл {relative_name} содержит некорректный Python: {exc}") from exc
        sources[relative_name] = old_text
        checked.append((relative, old, new, old_text))

    if set(file_patches) != seen:
        missing = sorted(seen - set(file_patches))
        extra = sorted(set(file_patches) - seen)
        raise ProposalTestError(
            f"Состав diff не совпадает с манифестом. Нет в diff: {missing}; лишние: {extra}."
        )
    if len(seen) > 1:
        has_source = any(not _is_test_module_path(path) for path in seen)
        has_test = any(
            _is_test_module_path(path)
            for path in seen
        )
        if not has_source or not has_test:
            raise ProposalTestError(
                "Многофайловый пакет должен включать изменение программы и тест tests/test_*.py."
            )

    try:
        reconstructed_files = apply_multi_file_unified_diff(sources, patch_text)
    except ValueError as exc:
        raise ProposalTestError(f"Diff не совпадает с исходниками: {exc}") from exc
    def _normalize_diff_result(value: str) -> str:
        # A unified diff may omit only the final newline marker. Preserve strict
        # comparison of every actual source line while accepting CRLF/LF variants.
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        return normalized[:-1] if normalized.endswith("\n") else normalized

    for relative, _old, new, _old_text in checked:
        name = relative.as_posix()
        try:
            updated_text = new.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProposalTestError(f"Файл предложения {name} не является UTF-8.") from exc
        reconstructed = reconstructed_files.get(name)
        if reconstructed is None or _normalize_diff_result(reconstructed) != _normalize_diff_result(updated_text):
            raise ProposalTestError(f"Сохранённый diff не соответствует содержимому файла {name}.")

    report: dict[str, Any] = {
        "schema": 1, "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": False, "checked_files": len(checked), "tests_exit_code": None,
        "tests_run": 0, "failures": 0, "errors": 0, "stdout": "", "stderr": "",
        "error": "", "sandboxed": False, "sandbox": "Windows Sandbox",
    }
    workspace = Path(tempfile.mkdtemp(prefix="moya_sandbox_test_", dir=str(get_temp_directory("self_development"))))
    keep_workspace = False
    try:
        readonly_root = workspace / "readonly"
        writable_root = workspace / "results"
        project_copy = readonly_root / "Project"
        readonly_root.mkdir(parents=True, exist_ok=False)
        writable_root.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source, project_copy, ignore=_ignore_sandbox_copy)
        for relative, _old, updated, _old_text in checked:
            destination = project_copy / Path(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(updated)

        if sandbox_executor is None:
            sandbox_report = _run_windows_sandbox(readonly_root, writable_root, timeout_seconds=timeout_seconds)
        else:
            sandbox_report = sandbox_executor(project_copy, writable_root, timeout_seconds)
        if not isinstance(sandbox_report, dict):
            raise ProposalTestError("Тестовый исполнитель вернул неверный формат отчёта.")
        report.update(
            passed=bool(sandbox_report.get("passed")),
            tests_exit_code=sandbox_report.get("tests_exit_code"),
            tests_run=int(sandbox_report.get("tests_run", 0) or 0),
            failures=int(sandbox_report.get("failures", 0) or 0),
            errors=int(sandbox_report.get("errors", 0) or 0),
            stdout=str(sandbox_report.get("stdout", ""))[-12000:],
            stderr=str(sandbox_report.get("stderr", ""))[-12000:],
            error=str(sandbox_report.get("error", ""))[:2000],
            sandboxed=bool(sandbox_report.get("sandboxed", False)),
            sandbox_details={
                "networking": sandbox_report.get("networking", "disabled" if sandbox_report.get("sandboxed") else "test_executor"),
                "project_mapping": sandbox_report.get("project_mapping", "read_only" if sandbox_report.get("sandboxed") else "test_executor"),
                "writable_host_mapping": sandbox_report.get("writable_host_mapping", "dedicated_results_only" if sandbox_report.get("sandboxed") else "test_executor"),
            },
        )
        report["passed"] = (
            report["passed"]
            and report["tests_run"] > 0
            and report["tests_exit_code"] == 0
            and report["failures"] == 0
            and report["errors"] == 0
            and (sandbox_executor is not None or report["sandboxed"] is True)
        )
        if not report["tests_run"] and not report["error"]:
            report["error"] = "В копии проекта не найдено ни одного unit-теста."
        if sandbox_report.get("workspace_must_be_kept"):
            keep_workspace = True
            report["workspace_path"] = str(workspace)
        elif sandbox_executor is None:
            time.sleep(3)
    except subprocess.TimeoutExpired as exc:
        report["error"] = f"Превышено время выполнения тестов ({exc.timeout} секунд)."
        report["stdout"] = str(exc.stdout or "")[-12000:]
        report["stderr"] = str(exc.stderr or "")[-12000:]
    except ProposalTestError as exc:
        report["error"] = str(exc)
        if "оставлен для диагностики" in str(exc):
            keep_workspace = True
            report["workspace_path"] = str(workspace)
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        if not keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)

    report_path = bundle / "test_report.json"
    _write_text_atomic(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    manifest["test"] = {
        "status": "passed" if report["passed"] else "failed",
        "tested_at": report["tested_at"], "report": "test_report.json",
        "sandboxed": bool(report.get("sandboxed")),
    }
    _write_text_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    report["report_path"] = str(report_path)
    return report



def _current_windows_user_sid() -> bytes | None:
    """Read the actual current process token SID; environment variables are not identity."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        token = wintypes.HANDLE()
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
        advapi32.GetLengthSid.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            return None
        try:
            required = wintypes.DWORD(0)
            advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
            if required.value <= 0 or required.value > 64 * 1024:
                return None
            buffer = ctypes.create_string_buffer(required.value)
            if not advapi32.GetTokenInformation(
                token, 1, ctypes.cast(buffer, ctypes.c_void_p),
                required.value, ctypes.byref(required),
            ):
                return None

            class _SidAndAttributes(ctypes.Structure):
                _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

            class _TokenUser(ctypes.Structure):
                _fields_ = [("User", _SidAndAttributes)]

            user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
            sid_length = int(advapi32.GetLengthSid(user.User.Sid) or 0)
            if sid_length <= 0 or sid_length > 1024:
                return None
            return ctypes.string_at(user.User.Sid, sid_length)
        finally:
            kernel32.CloseHandle(token)
    except Exception:
        return None


def _lookup_local_windows_account_sid(account_name: str) -> bytes | None:
    """Resolve a local Windows account SID using the system account database."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.LookupAccountNameW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.LookupAccountNameW.restype = wintypes.BOOL
        for qualified_name in (".\\" + account_name, account_name):
            sid_size = wintypes.DWORD(0)
            domain_size = wintypes.DWORD(0)
            use = wintypes.DWORD(0)
            advapi32.LookupAccountNameW(
                None, qualified_name, None, ctypes.byref(sid_size),
                None, ctypes.byref(domain_size), ctypes.byref(use),
            )
            if sid_size.value <= 0 or sid_size.value > 1024:
                continue
            sid_buffer = ctypes.create_string_buffer(sid_size.value)
            domain_buffer = ctypes.create_unicode_buffer(max(1, domain_size.value))
            if not advapi32.LookupAccountNameW(
                None, qualified_name, ctypes.cast(sid_buffer, ctypes.c_void_p),
                ctypes.byref(sid_size), domain_buffer, ctypes.byref(domain_size),
                ctypes.byref(use),
            ):
                continue
            return ctypes.string_at(sid_buffer, sid_size.value)
    except Exception:
        return None
    return None


def _is_windows_sandbox_guest() -> bool:
    """Require the actual WDAG guest account SID and a marker set by the WSB logon script."""
    if os.name != "nt" or os.environ.get("MOYA_WINDOWS_SANDBOX", "") != "1":
        return False
    current_sid = _current_windows_user_sid()
    guest_sid = _lookup_local_windows_account_sid("WDAGUtilityAccount")
    return bool(current_sid and guest_sid and current_sid == guest_sid)


def run_proposal_tests_cli(project_root: str | Path, result_path: str | Path) -> int:
    """Entry point used by the frozen EXE guest runner to test source files from the mapped project."""
    import importlib.machinery
    import unittest

    if not _is_windows_sandbox_guest():
        # This CLI is deliberately unusable as a host-side test runner.
        return 3
    root = Path(project_root).expanduser().resolve()
    output_path = Path(result_path).expanduser().resolve()
    result_data: dict[str, Any] = {
        "passed": False, "stdout": "", "stderr": "", "tests_run": 0,
        "failures": 0, "errors": 0,
    }
    stream = __import__("io").StringIO()
    old_cwd = Path.cwd()
    original_meta_path = list(sys.meta_path)
    try:
        os.chdir(root)
        sys.path.insert(0, str(root))
        # Prefer proposed source files over the modules frozen into the EXE.
        sys.meta_path = [
            importlib.machinery.PathFinder,
            *[finder for finder in sys.meta_path if finder is not importlib.machinery.PathFinder],
        ]
        project_modules = {
            path.stem for path in root.rglob("*.py")
            if path.is_file() and "tests" not in path.relative_to(root).parts
        }
        for module_name in project_modules:
            sys.modules.pop(module_name, None)
        loader = unittest.TestLoader()
        suite = loader.discover(str(root / "tests"), pattern="test_*.py", top_level_dir=str(root))
        test_result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        result_data.update(
            passed=test_result.wasSuccessful() and test_result.testsRun > 0,
            tests_run=test_result.testsRun,
            failures=len(test_result.failures),
            errors=len(test_result.errors),
            stdout=stream.getvalue()[-12000:],
        )
    except Exception as exc:
        result_data["stderr"] = str(exc)[:12000]
    finally:
        try:
            os.chdir(old_cwd)
        except OSError:
            pass
        try:
            sys.meta_path = original_meta_path
            if str(root) in sys.path:
                sys.path.remove(str(root))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return 2
    return 0 if result_data.get("passed") else 1

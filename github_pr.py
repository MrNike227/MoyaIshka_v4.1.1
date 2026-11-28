# -*- coding: utf-8 -*-
"""Create review-only GitHub Draft PRs from self-improvement patches.

This module deliberately has no release, tag, merge, or direct-to-default-branch
operation. A proposal is first rebased against the selected GitHub base file.
"""
from __future__ import annotations

# Standard library
import base64
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

# Application module
from self_improvement import apply_unified_diff, split_multi_file_unified_diff

API_ROOT = "https://api.github.com"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")


class GitHubProposalError(RuntimeError):
    pass


def _api_request(
    token: str,
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 25.0,
) -> dict[str, Any]:
    if not token or len(token) > 500:
        raise GitHubProposalError("Добавь GitHub Personal Access Token в настройках саморазвития.")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        API_ROOT + endpoint,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "MoyaIshka self-development client",
            "Content-Type": "application/json",
        },
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=max(3.0, min(float(timeout), 60.0))) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise GitHubProposalError("Ответ GitHub превышает допустимый размер.")
        value = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(value, dict):
            raise GitHubProposalError("GitHub вернул ответ неожиданного формата.")
        return value
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read(20000).decode("utf-8", errors="replace")
            detail = json.loads(error_body).get("message", "")
        except Exception:
            detail = ""
        if exc.code in {401, 403}:
            raise GitHubProposalError("GitHub отклонил токен или у токена недостаточно прав. Проверь Contents: Read and write и Pull requests: Read and write.") from exc
        if exc.code == 404:
            raise GitHubProposalError("GitHub не нашёл репозиторий, базовую ветку или файл. Проверь имя репозитория и права токена.") from exc
        raise GitHubProposalError(f"GitHub API вернул HTTP {exc.code}: {str(detail)[:500]}") from exc
    except urllib.error.URLError as exc:
        raise GitHubProposalError(f"Не удалось подключиться к GitHub: {exc.reason}") from exc
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise GitHubProposalError(f"Не удалось обработать ответ GitHub: {exc}") from exc


def _safe_repo_path(value: str) -> str:
    path = str(value or "").replace("\\", "/").strip()
    parts = path.split("/")
    reserved_names = {
        "con", "prn", "aux", "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
    invalid_windows_component = any(
        part.endswith((" ", "."))
        or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
        or part.split(".", 1)[0].casefold() in reserved_names
        for part in parts
    )
    if (
        not path
        or path.startswith("/")
        or any(part in {"", ".", ".."} or ":" in part for part in parts)
        or invalid_windows_component
        or (parts and parts[0].casefold() in {".git", ".github"})
        or not path.lower().endswith(".py")
    ):
        raise GitHubProposalError("Draft PR разрешено создавать только для безопасного относительного пути к Python-файлу.")
    return path


def create_draft_pull_request(
    repository: str,
    token: str,
    base_branch: str,
    file_path: str,
    patch_text: str,
    *,
    title: str = "Предложение улучшения от ISH",
    body: str = "",
    request: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rebase one file patch onto GitHub base and open a Draft PR (never a release)."""
    repo = str(repository or "").strip().strip("/")
    if not _REPO_RE.fullmatch(repo):
        raise GitHubProposalError("Укажи GitHub-репозиторий в формате owner/repository.")
    if not token:
        raise GitHubProposalError("Для создания Draft PR нужен GitHub Personal Access Token.")
    base = str(base_branch or "").strip()
    if base and (not _BRANCH_RE.fullmatch(base) or base.startswith("/") or ".." in base.split("/")):
        raise GitHubProposalError("Указана небезопасная базовая ветка.")
    path = _safe_repo_path(file_path)
    patch = str(patch_text or "").strip()
    if not patch or len(patch.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise GitHubProposalError("Diff пустой или превышает 2 МБ.")
    api = request or _api_request
    prefix = "/repos/" + repo

    repo_info = api(token, "GET", prefix)
    if not base:
        base = str(repo_info.get("default_branch") or "main")
    ref = api(token, "GET", prefix + "/git/ref/heads/" + urllib.parse.quote(base, safe="/"))
    base_sha = str(ref.get("object", {}).get("sha", ""))
    if not base_sha:
        raise GitHubProposalError("Не удалось определить последний коммит базовой ветки.")
    base_commit = api(token, "GET", prefix + "/git/commits/" + base_sha)
    base_tree = str(base_commit.get("tree", {}).get("sha", ""))
    if not base_tree:
        raise GitHubProposalError("GitHub не вернул дерево базового коммита.")

    content_endpoint = prefix + "/contents/" + urllib.parse.quote(path, safe="/") + "?ref=" + urllib.parse.quote(base, safe="")
    content_result = api(token, "GET", content_endpoint)
    if str(content_result.get("encoding", "")).lower() != "base64":
        raise GitHubProposalError("GitHub вернул файл в неподдерживаемой кодировке.")
    try:
        original_bytes = base64.b64decode("".join(str(content_result.get("content", "")).split()), validate=True)
        if len(original_bytes) > MAX_SOURCE_BYTES:
            raise GitHubProposalError("Исходный файл на GitHub превышает лимит 2 МБ.")
        original = original_bytes.decode("utf-8")
        updated = apply_unified_diff(original, patch, path)
        compile(updated, path, "exec")
    except GitHubProposalError:
        raise
    except Exception as exc:
        raise GitHubProposalError(
            "Diff не удалось безопасно применить к текущей версии файла на GitHub. "
            "Сначала обнови локальные исходники и подготовь diff заново."
        ) from exc
    if updated == original:
        raise GitHubProposalError("Diff не изменяет файл; пустой PR не создан.")

    blob = api(token, "POST", prefix + "/git/blobs", {"content": updated, "encoding": "utf-8"})
    blob_sha = str(blob.get("sha", ""))
    if not blob_sha:
        raise GitHubProposalError("GitHub не создал blob с изменённым файлом.")
    tree = api(token, "POST", prefix + "/git/trees", {
        "base_tree": base_tree,
        "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}],
    })
    tree_sha = str(tree.get("sha", ""))
    if not tree_sha:
        raise GitHubProposalError("GitHub не создал дерево изменений.")
    timestamp = uuid.uuid4().hex[:10]
    branch = f"moya-improvement/{timestamp}"
    commit = api(token, "POST", prefix + "/git/commits", {
        "message": str(title).strip()[:120] or "Propose code improvement",
        "tree": tree_sha,
        "parents": [base_sha],
    })
    commit_sha = str(commit.get("sha", ""))
    if not commit_sha:
        raise GitHubProposalError("GitHub не создал коммит для предложения.")
    api(token, "POST", prefix + "/git/refs", {
        "ref": "refs/heads/" + branch,
        "sha": commit_sha,
    })
    pr_body = (
        "Это Draft PR, автоматически подготовленный модулем саморазвития ISH.\n\n"
        "Изменения рассчитаны относительно актуального файла базовой ветки. "
        "Проверь код и запусти CI перед слиянием.\n\n"
        + str(body).strip()[:4000]
    )
    try:
        pr = api(token, "POST", prefix + "/pulls", {
            "title": str(title).strip()[:200] or "Предложение улучшения от ISH",
            "head": branch,
            "base": base,
            "body": pr_body,
            "draft": True,
        })
    except Exception:
        try:
            api(token, "DELETE", prefix + "/git/refs/heads/" + urllib.parse.quote(branch, safe="/"))
        except Exception:
            pass
        raise
    if not pr.get("html_url") or not pr.get("number"):
        raise GitHubProposalError("GitHub не подтвердил создание Draft PR.")
    return {
        "number": int(pr["number"]),
        "url": str(pr["html_url"]),
        "branch": branch,
        "base": base,
        "repository": repo,
        "draft": bool(pr.get("draft", True)),
    }


MAX_BUNDLE_FILES = 10
MAX_BUNDLE_FILE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_TOTAL_BYTES = 8 * 1024 * 1024


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise GitHubProposalError(f"Не удалось безопасно проверить путь пакета: {exc}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _read_bundle_file(root: Path, relative: str, limit: int) -> bytes:
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if os.path.lexists(candidate) and _is_reparse_point(candidate):
            raise GitHubProposalError(f"Пакет содержит ссылку или reparse point: {relative}.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise GitHubProposalError(f"Не найден файл проверенного пакета: {relative}.") from exc
    if root not in resolved.parents or not resolved.is_file():
        raise GitHubProposalError(f"Файл пакета выходит за пределы папки или не является файлом: {relative}.")
    try:
        if resolved.stat().st_size > limit:
            raise GitHubProposalError(f"Файл пакета превышает безопасный размер: {relative}.")
        return resolved.read_bytes()
    except OSError as exc:
        raise GitHubProposalError(f"Не удалось прочитать файл пакета {relative}: {exc}") from exc


def _safe_bundle_path(value: str) -> str:
    path = _safe_repo_path(value)
    parts = path.split("/")
    forbidden = {".git", ".github", "__pycache__", ".venv", "venv", "build", "dist"}
    if any(part.casefold() in forbidden for part in parts):
        raise GitHubProposalError(f"Изменение служебного или сборочного пути запрещено: {path}.")
    if parts[0].casefold() == "tests" and not parts[-1].casefold().startswith("test_"):
        raise GitHubProposalError("В папке tests разрешено изменять только tests/test_*.py.")
    return path


def _normalized_sha256(raw: bytes) -> str:
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def load_tested_proposal_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Revalidate a saved bundle and require a passing, confirmed Windows Sandbox report."""
    supplied = Path(bundle_dir).expanduser()
    if not supplied.exists() or _is_reparse_point(supplied):
        raise GitHubProposalError("Папка предложения отсутствует или является ссылкой.")
    try:
        root = supplied.resolve(strict=True)
    except OSError as exc:
        raise GitHubProposalError(f"Не удалось открыть папку предложения: {exc}") from exc
    if not root.is_dir():
        raise GitHubProposalError("Предложение должно быть папкой пакета в Updates/Proposals.")

    try:
        manifest = json.loads(_read_bundle_file(root, "manifest.json", 128 * 1024).decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise GitHubProposalError(f"Манифест предложения повреждён: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise GitHubProposalError("Манифест предложения имеет неизвестный формат.")
    if manifest.get("status") != "review_only_not_applied":
        raise GitHubProposalError("Можно отправлять только сохранённые предложения, ещё не применённые к приложению.")

    entries = manifest.get("files")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_BUNDLE_FILES:
        raise GitHubProposalError(f"Пакет должен содержать от 1 до {MAX_BUNDLE_FILES} Python-файлов.")

    test_meta = manifest.get("test")
    if (
        not isinstance(test_meta, dict)
        or test_meta.get("status") != "passed"
        or test_meta.get("report") != "test_report.json"
        or test_meta.get("sandboxed") is not True
    ):
        raise GitHubProposalError(
            "Сначала успешно протестируй предложение в настоящей Windows Sandbox. "
            "Проверка обычным Python на основном компьютере для отправки PR не подходит."
        )
    try:
        report = json.loads(_read_bundle_file(root, "test_report.json", 1024 * 1024).decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise GitHubProposalError(f"Отчёт тестирования повреждён: {exc}") from exc
    if (
        not isinstance(report, dict)
        or report.get("schema") != 1
        or report.get("passed") is not True
        or report.get("sandboxed") is not True
        or type(report.get("tests_exit_code")) is not int
        or report.get("tests_exit_code") != 0
        or type(report.get("tests_run")) is not int
        or report["tests_run"] < 1
        or type(report.get("failures")) is not int
        or report["failures"] != 0
        or type(report.get("errors")) is not int
        or report["errors"] != 0
        or type(report.get("checked_files")) is not int
        or report["checked_files"] != len(entries)
    ):
        raise GitHubProposalError("Отчёт не подтверждает успешный запуск unit-тестов в Windows Sandbox.")

    patch_meta = manifest.get("patch")
    if not isinstance(patch_meta, dict) or patch_meta.get("path") != "changes.patch":
        raise GitHubProposalError("В манифесте отсутствует корректная ссылка на diff.")
    patch_bytes = _read_bundle_file(root, "changes.patch", MAX_SOURCE_BYTES)
    if (
        len(patch_bytes) != patch_meta.get("size")
        or hashlib.sha256(patch_bytes).hexdigest() != patch_meta.get("sha256")
    ):
        raise GitHubProposalError("Контрольная сумма diff не совпадает.")
    try:
        patch_text = patch_bytes.decode("utf-8")
        patches = split_multi_file_unified_diff(patch_text)
    except (UnicodeError, ValueError) as exc:
        raise GitHubProposalError(f"Многофайловый diff повреждён: {exc}") from exc

    seen: set[str] = set()
    seen_casefolded: set[str] = set()
    file_payloads: dict[str, bytes] = {}
    total = len(patch_bytes)
    for entry in entries:
        if not isinstance(entry, dict):
            raise GitHubProposalError("Запись файла в манифесте имеет неверный формат.")
        path = _safe_bundle_path(str(entry.get("path", "")))
        folded_path = path.casefold()
        if folded_path in seen_casefolded:
            raise GitHubProposalError(
                f"Файл {path} повторяется или отличается только регистром; Windows считает такие пути одним файлом."
            )
        seen.add(path)
        seen_casefolded.add(folded_path)
        updated = _read_bundle_file(root, "files/" + path, MAX_BUNDLE_FILE_BYTES)
        if len(updated) != entry.get("size") or hashlib.sha256(updated).hexdigest() != entry.get("sha256"):
            raise GitHubProposalError(f"Размер или SHA-256 изменённого файла не совпадает: {path}.")
        try:
            compile(updated.decode("utf-8"), path, "exec")
        except (UnicodeError, SyntaxError) as exc:
            raise GitHubProposalError(f"Файл {path} содержит некорректный Python: {exc}") from exc
        base_hash = entry.get("base_sha256")
        if base_hash == "absent":
            if not (path.split("/", 1)[0].casefold() == "tests" and Path(path).name.casefold().startswith("test_")):
                raise GitHubProposalError("Новые файлы разрешено добавлять только как tests/test_*.py.")
        elif not isinstance(base_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", base_hash):
            raise GitHubProposalError(f"В манифесте указан неверный base SHA-256: {path}.")
        total += len(updated)
        if total > MAX_BUNDLE_TOTAL_BYTES:
            raise GitHubProposalError("Пакет предложения превышает общий лимит 8 МБ.")
        file_payloads[path] = updated

    if set(patches) != seen:
        missing = sorted(seen - set(patches))
        extra = sorted(set(patches) - seen)
        raise GitHubProposalError(
            f"Состав diff не совпадает с манифестом. Нет в diff: {missing}; лишние: {extra}."
        )
    if len(seen) > 1:
        has_source = any(not (path.split("/", 1)[0].casefold() == "tests" and Path(path).name.casefold().startswith("test_")) for path in seen)
        has_test = any(path.split("/", 1)[0].casefold() == "tests" and Path(path).name.casefold().startswith("test_") for path in seen)
        if not has_source or not has_test:
            raise GitHubProposalError("Многофайловый пакет должен содержать программу и тест tests/test_*.py.")

    return {
        "root": root,
        "manifest": manifest,
        "report": report,
        "patch_text": patch_text,
        "patches": patches,
        "files": file_payloads,
        "entries": {str(item["path"]): item for item in entries},
    }


def find_matching_tested_proposal_bundle(updates_dir: str | Path, patch_text: str) -> Path | None:
    """Locate a saved, passing bundle that exactly matches the diff currently shown in the UI."""
    proposals = Path(updates_dir).expanduser() / "Proposals"
    if not proposals.is_dir() or _is_reparse_point(proposals):
        return None
    expected = patch_text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    matches: list[Path] = []
    try:
        candidates = list(proposals.iterdir())
    except OSError:
        return None
    for candidate in candidates:
        try:
            if not candidate.is_dir() or candidate.name in {"Inbox"} or candidate.name.startswith("."):
                continue
            bundle = load_tested_proposal_bundle(candidate)
            saved = bundle["patch_text"].replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
            if saved == expected:
                matches.append(candidate)
        except (OSError, ValueError, GitHubProposalError):
            continue
    return max(matches, key=lambda item: item.stat().st_mtime) if matches else None


def create_draft_pull_request_from_bundle(
    repository: str,
    token: str,
    base_branch: str,
    bundle_dir: str | Path,
    *,
    title: str = "Проверенное предложение саморазвития",
    body: str = "",
    request: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create one Draft PR with all files from a Sandbox-tested proposal bundle."""
    repo = str(repository or "").strip().strip("/")
    if not _REPO_RE.fullmatch(repo):
        raise GitHubProposalError("Укажи GitHub-репозиторий в формате owner/repository.")
    if not token:
        raise GitHubProposalError("Для создания Draft PR нужен GitHub Personal Access Token.")
    base = str(base_branch or "").strip()
    if base and (not _BRANCH_RE.fullmatch(base) or base.startswith("/") or ".." in base.split("/")):
        raise GitHubProposalError("Указана небезопасная базовая ветка.")

    bundle = load_tested_proposal_bundle(bundle_dir)
    api = request or _api_request
    prefix = "/repos/" + repo
    repo_info = api(token, "GET", prefix)
    if not base:
        base = str(repo_info.get("default_branch") or "main")
    ref = api(token, "GET", prefix + "/git/ref/heads/" + urllib.parse.quote(base, safe="/"))
    base_sha = str(ref.get("object", {}).get("sha", ""))
    if not base_sha:
        raise GitHubProposalError("Не удалось определить последний коммит базовой ветки.")
    base_commit = api(token, "GET", prefix + "/git/commits/" + base_sha)
    base_tree = str(base_commit.get("tree", {}).get("sha", ""))
    if not base_tree:
        raise GitHubProposalError("GitHub не вернул дерево базового коммита.")

    tree_entries: list[dict[str, str]] = []
    for path, saved_bytes in bundle["files"].items():
        entry = bundle["entries"][path]
        content_endpoint = (
            prefix + "/contents/" + urllib.parse.quote(path, safe="/")
            + "?ref=" + urllib.parse.quote(base, safe="")
        )
        if entry.get("base_sha256") == "absent":
            try:
                api(token, "GET", content_endpoint)
            except GitHubProposalError as exc:
                if "не нашёл репозиторий" not in str(exc):
                    raise
            else:
                raise GitHubProposalError(
                    f"Новый тестовый файл {path} уже существует в базовой ветке. Пересоздай предложение."
                )
            original = ""
        else:
            content_result = api(token, "GET", content_endpoint)
            if str(content_result.get("encoding", "")).lower() != "base64":
                raise GitHubProposalError(f"GitHub вернул файл {path} в неподдерживаемой кодировке.")
            try:
                original_bytes = base64.b64decode(
                    "".join(str(content_result.get("content", "")).split()), validate=True
                )
                original = original_bytes.decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubProposalError(f"Не удалось прочитать исходный файл {path} на GitHub.") from exc
            if _normalized_sha256(original_bytes) != entry.get("base_sha256"):
                raise GitHubProposalError(
                    f"Файл {path} на GitHub изменился после тестирования предложения. "
                    "Повтори саморазвитие и проверку в Windows Sandbox."
                )

        try:
            updated = apply_unified_diff(original, bundle["patches"][path], path)
            compile(updated, path, "exec")
        except Exception as exc:
            raise GitHubProposalError(
                f"Diff для {path} не совпадает с актуальной базовой веткой GitHub: {exc}"
            ) from exc
        if _normalized_sha256(updated.encode("utf-8")) != _normalized_sha256(saved_bytes):
            raise GitHubProposalError(
                f"Содержимое файла {path} не совпадает с протестированным пакетом. Draft PR не создан."
            )
        blob = api(token, "POST", prefix + "/git/blobs", {
            "content": updated,
            "encoding": "utf-8",
        })
        blob_sha = str(blob.get("sha", ""))
        if not blob_sha:
            raise GitHubProposalError(f"GitHub не создал blob для файла {path}.")
        tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

    tree = api(token, "POST", prefix + "/git/trees", {
        "base_tree": base_tree,
        "tree": tree_entries,
    })
    tree_sha = str(tree.get("sha", ""))
    if not tree_sha:
        raise GitHubProposalError("GitHub не создал дерево многофайловых изменений.")
    version_label = re.sub(
        r"[^A-Za-z0-9._-]+", "-", str(bundle["manifest"].get("version", "")).strip()
    )[:40] or "proposal"
    branch = "moya-improvement/" + version_label + "/" + uuid.uuid4().hex[:10]
    commit = api(token, "POST", prefix + "/git/commits", {
        "message": str(title).strip()[:120] or "Propose tested multi-file improvement",
        "tree": tree_sha,
        "parents": [base_sha],
    })
    commit_sha = str(commit.get("sha", ""))
    if not commit_sha:
        raise GitHubProposalError("GitHub не создал коммит для проверенного предложения.")
    api(token, "POST", prefix + "/git/refs", {
        "ref": "refs/heads/" + branch,
        "sha": commit_sha,
    })
    file_list = "\n".join("- " + path for path in bundle["files"])
    test_count = int(bundle["report"].get("tests_run", 0) or 0)
    pr_body = (
        "Это Draft PR, созданный из сохранённого предложения саморазвития ISH.\n\n"
        "Пакет повторно проверен по SHA-256 и применён к актуальным файлам базовой ветки. "
        "Отчёт подтверждает успешное выполнение unit-тестов внутри Windows Sandbox.\n\n"
        f"Проверено тестов: {test_count}\n\nИзменённые файлы:\n{file_list}\n\n"
        + str(body).strip()[:4000]
    )
    try:
        pr = api(token, "POST", prefix + "/pulls", {
            "title": str(title).strip()[:200] or "Проверенное предложение саморазвития",
            "head": branch,
            "base": base,
            "body": pr_body,
            "draft": True,
        })
    except Exception:
        try:
            api(token, "DELETE", prefix + "/git/refs/heads/" + urllib.parse.quote(branch, safe="/"))
        except Exception:
            pass
        raise
    if not pr.get("html_url") or not pr.get("number"):
        raise GitHubProposalError("GitHub не подтвердил создание многофайлового Draft PR.")
    return {
        "number": int(pr["number"]),
        "url": str(pr["html_url"]),
        "branch": branch,
        "base": base,
        "repository": repo,
        "draft": bool(pr.get("draft", True)),
        "files": list(bundle["files"]),
        "tests_run": test_count,
        "sandboxed": True,
    }


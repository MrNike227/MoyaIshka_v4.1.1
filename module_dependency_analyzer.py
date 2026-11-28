# -*- coding: utf-8 -*-
"""Static Python import graph for estimating the impact of self-improvement proposals."""
from __future__ import annotations

import ast
import os
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any

MAX_ANALYZED_FILES = 1200
MAX_SOURCE_BYTES = 1_000_000
SKIP_DIRECTORIES = {
    ".git", ".github", ".venv", "venv", "__pycache__", "build", "dist",
    ".pytest_cache", ".mypy_cache", "node_modules", "site-packages",
}


def _module_name(relative_path: str) -> str:
    parts = list(PurePosixPath(relative_path).parts)
    if not parts:
        return ""
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = PurePosixPath(parts[-1]).stem
    return ".".join(parts)


def _safe_python_files(root: Path, warnings: list[str]) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    root = root.resolve()
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name.casefold() not in SKIP_DIRECTORIES
            and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            if not filename.casefold().endswith(".py"):
                continue
            candidate = current_path / filename
            try:
                if candidate.is_symlink():
                    continue
                resolved = candidate.resolve()
                if root not in resolved.parents or not resolved.is_file():
                    continue
                if resolved.stat().st_size > MAX_SOURCE_BYTES:
                    warnings.append(
                        f"{resolved.relative_to(root).as_posix()}: пропущен файл больше 1 МБ."
                    )
                    continue
                relative = resolved.relative_to(root).as_posix()
                result.append((relative, resolved))
                if len(result) >= MAX_ANALYZED_FILES:
                    warnings.append(
                        f"Достигнут предел анализа: {MAX_ANALYZED_FILES} Python-файлов."
                    )
                    return result
            except OSError:
                continue
    return result


def _resolve_import_candidates(
    current_module: str,
    relative_path: str,
    module: str | None,
    level: int,
    names: list[str],
    module_to_path: dict[str, str],
) -> set[str]:
    if level:
        is_package_init = PurePosixPath(relative_path).name == "__init__.py"
        package_parts = current_module.split(".") if is_package_init else current_module.split(".")[:-1]
        trim = max(0, int(level) - 1)
        if trim > len(package_parts):
            return set()
        base_parts = package_parts[:len(package_parts) - trim]
        if module:
            base_parts.extend(part for part in module.split(".") if part)
        base_module = ".".join(base_parts)
    else:
        base_module = str(module or "").strip(".")

    candidates: set[str] = set()
    if base_module in module_to_path:
        candidates.add(base_module)
    for name in names:
        if name == "*":
            continue
        full_name = ".".join(part for part in (base_module, name) if part)
        if full_name in module_to_path:
            candidates.add(full_name)
    return candidates


def _static_dynamic_import(
    node: ast.Call,
    current_module: str,
    relative_path: str,
    module_to_path: dict[str, str],
) -> tuple[set[str], bool]:
    function = node.func
    is_dynamic_import = (
        isinstance(function, ast.Name) and function.id == "__import__"
    ) or (
        isinstance(function, ast.Attribute) and function.attr == "import_module"
    )
    if not is_dynamic_import:
        return set(), False
    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        return set(), True
    raw_name = node.args[0].value
    if raw_name.startswith("."):
        package_value = None
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            package_value = node.args[1].value if isinstance(node.args[1].value, str) else None
        default_package = (
            current_module
            if PurePosixPath(relative_path).name == "__init__.py"
            else current_module.rpartition(".")[0]
        )
        package = str(package_value or default_package)
        parts = package.split(".") if package else []
        level = len(raw_name) - len(raw_name.lstrip("."))
        if level > len(parts) + 1:
            return set(), False
        base = parts[:len(parts) - max(0, level - 1)]
        raw_name = ".".join(base + [part for part in raw_name.lstrip(".").split(".") if part])
    return ({raw_name} if raw_name in module_to_path else set()), False


def analyze_module_dependencies(
    project_root: str | Path,
    target_relative_path: str,
) -> dict[str, Any]:
    """Build a bounded AST import graph and list modules/tests that may be affected."""
    root = Path(project_root).expanduser().resolve()
    relative = str(target_relative_path).replace("\\", "/").strip()
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in pure.parts)
        or pure.suffix.casefold() != ".py"
    ):
        raise ValueError("Для анализа связей укажи относительный путь к Python-модулю.")
    target = root.joinpath(*pure.parts)
    if target.is_symlink() or not target.is_file() or root not in target.resolve().parents:
        raise ValueError("Выбранный модуль отсутствует или находится вне проекта.")
    target_resolved = target.resolve()
    relative = target_resolved.relative_to(root).as_posix()
    warnings: list[str] = []
    files = _safe_python_files(root, warnings)

    path_to_module: dict[str, str] = {}
    module_to_path: dict[str, str] = {}
    for path, _full_path in files:
        module_name = _module_name(path)
        if not module_name:
            continue
        path_to_module[path] = module_name
        # The first stable match wins if a project has both a module and a
        # package initializer with the same import name.
        module_to_path.setdefault(module_name, path)

    if relative not in path_to_module:
        raise ValueError("Выбранный модуль не удалось включить в карту Python-импортов.")
    target_module = path_to_module[relative]

    # Parse one file at a time. Retaining every AST and source string until the
    # graph is complete can consume several gigabytes on large projects.
    edges: dict[str, set[str]] = {}
    imported_names_by_path: dict[str, set[str]] = defaultdict(set)
    parsed_paths: list[str] = []
    for path, full_path in files:
        current_module = path_to_module.get(path)
        if not current_module:
            continue
        try:
            source = full_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path)
        except (OSError, UnicodeError, SyntaxError) as exc:
            warnings.append(f"{path}: не удалось разобрать статические импорты ({type(exc).__name__}).")
            continue

        parsed_paths.append(path)
        module_edges: set[str] = set()
        for node in ast.walk(tree):
            candidates: set[str] = set()
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in module_to_path:
                        candidates.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
                candidates.update(_resolve_import_candidates(
                    current_module, path, node.module, node.level, names, module_to_path,
                ))
                if node.module:
                    imported_names_by_path[path].update(
                        alias.name for alias in node.names if alias.name != "*"
                    )
            elif isinstance(node, ast.Call):
                dynamic_candidates, unresolved = _static_dynamic_import(
                    node, current_module, path, module_to_path,
                )
                candidates.update(dynamic_candidates)
                function = node.func
                is_dynamic_import = (
                    isinstance(function, ast.Name) and function.id == "__import__"
                ) or (
                    isinstance(function, ast.Attribute) and function.attr == "import_module"
                )
                if unresolved:
                    warnings.append(
                        f"{path}:{getattr(node, 'lineno', 1)}: динамический импорт нельзя определить статически."
                    )
                elif is_dynamic_import and not dynamic_candidates:
                    warnings.append(
                        f"{path}:{getattr(node, 'lineno', 1)}: импорт может выходить за пределы карты проекта."
                    )
            for imported_module in candidates:
                imported_path = module_to_path.get(imported_module)
                if imported_path and imported_path != path:
                    module_edges.add(imported_path)
        edges[path] = module_edges

    reverse: dict[str, set[str]] = defaultdict(set)
    for source_path, destinations in edges.items():
        for destination in destinations:
            reverse[destination].add(source_path)

    def walk(start: str, graph: dict[str, set[str]]) -> list[str]:
        found: set[str] = set()
        pending = deque(sorted(graph.get(start, set())))
        while pending:
            item = pending.popleft()
            if item == start or item in found:
                continue
            found.add(item)
            pending.extend(sorted(graph.get(item, set()) - found))
        return sorted(found)

    direct_dependencies = sorted(edges.get(relative, set()))
    transitive_dependencies = walk(relative, edges)
    def is_test_module(path: str) -> bool:
        parts = PurePosixPath(path).parts
        return bool(parts and parts[0].casefold() == "tests" and PurePosixPath(path).name.startswith("test_"))

    direct_dependents = [path for path in sorted(reverse.get(relative, set())) if not is_test_module(path)]
    transitive_dependents = [path for path in walk(relative, reverse) if not is_test_module(path)]
    affected_modules = sorted({relative, *direct_dependents, *transitive_dependents})
    tests = []
    for path in sorted(parsed_paths):
        parts = PurePosixPath(path).parts
        if not parts or parts[0].casefold() != "tests" or not PurePosixPath(path).name.startswith("test_"):
            continue
        if edges.get(path, set()).intersection(affected_modules):
            tests.append(path)

    def module_rows(paths: list[str]) -> list[dict[str, str]]:
        return [
            {"path": path, "module": path_to_module.get(path, "")}
            for path in paths
        ]

    imported_names = {
        path: sorted(names) for path, names in imported_names_by_path.items() if names
    }
    return {
        "target": relative,
        "target_module": target_module,
        "scanned_files": len(parsed_paths),
        "direct_dependencies": module_rows(direct_dependencies),
        "transitive_dependencies": module_rows(transitive_dependencies),
        "direct_dependents": module_rows(direct_dependents),
        "transitive_dependents": module_rows(transitive_dependents),
        "affected_modules": module_rows(affected_modules),
        "affected_tests": tests,
        "imported_names_by_path": imported_names,
        "warnings": sorted(set(warnings))[:30],
        "analysis_kind": "static_ast_import_graph",
    }


def format_dependency_report(analysis: dict[str, Any]) -> str:
    """Format the dependency graph as a compact Russian report for users and models."""
    def paths(key: str, limit: int = 12) -> str:
        items = [str(item.get("path", "")) for item in analysis.get(key, []) if isinstance(item, dict)]
        if len(items) > limit:
            return ", ".join(items[:limit]) + f" и ещё {len(items) - limit}"
        return ", ".join(items) if items else "не обнаружены"

    tests = [str(item) for item in analysis.get("affected_tests", [])]
    tests_text = ", ".join(tests[:12]) if tests else "не обнаружены"
    warnings = [str(item) for item in analysis.get("warnings", []) if item]
    report = [
        f"Целевой модуль: {analysis.get('target', '')}",
        f"Непосредственные импорты: {paths('direct_dependencies')}",
        f"Модули, которые напрямую используют его: {paths('direct_dependents')}",
        f"Косвенно затрагиваемые модули: {paths('transitive_dependents')}",
        f"Вероятно затронутые тесты: {tests_text}",
        f"Проанализировано Python-модулей: {int(analysis.get('scanned_files', 0) or 0)}",
        "Метод: статический разбор AST импортов; динамические связи могут быть не видны.",
    ]
    if warnings:
        report.append("Ограничения/предупреждения: " + " | ".join(warnings[:6]))
    return "\n".join(report)


def build_dependency_context(
    project_root: str | Path,
    analysis: dict[str, Any],
    *,
    prompt: str = "",
    max_chars: int = 6000,
) -> str:
    """Provide bounded import/API excerpts from modules around the selected target."""
    if max_chars < 500:
        return ""
    root = Path(project_root).expanduser().resolve()
    target = str(analysis.get("target", ""))
    rows: list[str] = []
    candidates: list[str] = []
    for key in ("direct_dependents", "direct_dependencies", "transitive_dependents", "affected_tests"):
        values = analysis.get(key, [])
        if key == "affected_tests":
            candidates.extend(str(value) for value in values if isinstance(value, str))
        else:
            candidates.extend(
                str(value.get("path", "")) for value in values if isinstance(value, dict)
            )
    unique: list[str] = []
    for path in candidates:
        if path and path != target and path not in unique:
            unique.append(path)
    imported_names = analysis.get("imported_names_by_path", {})
    used_chars = 0
    for relative in unique[:12]:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            continue
        path = root.joinpath(*pure.parts)
        try:
            if path.is_symlink() or root not in path.resolve().parents or path.stat().st_size > MAX_SOURCE_BYTES:
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError):
            continue
        lines = source.splitlines()
        excerpts = [f"\n### {relative}"]
        names = imported_names.get(relative, []) if isinstance(imported_names, dict) else []
        if names:
            excerpts.append("Имена, импортируемые этим модулем: " + ", ".join(names[:20]))
        import_lines = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and 1 <= node.lineno <= len(lines):
                import_lines.append((node.lineno, lines[node.lineno - 1].strip()))
        if import_lines:
            excerpts.append("Импорты: " + " | ".join(text for _, text in sorted(set(import_lines))[:10]))
        signatures = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                end = min(len(lines), max(node.lineno, min(node.body[0].lineno if node.body else node.lineno, node.lineno + 3)))
                signature = " ".join(line.strip() for line in lines[node.lineno - 1:end])
                signatures.append(signature[:350])
        if signatures:
            excerpts.append("Публичные точки взаимодействия: " + " | ".join(signatures[:12]))
        entry = "\n".join(excerpts)
        if used_chars + len(entry) > max_chars:
            available = max_chars - used_chars
            if available > 160:
                rows.append(entry[:available])
            break
        rows.append(entry)
        used_chars += len(entry)
    if not rows:
        return "Связанные исходники для дополнительного контекста не найдены."
    return "\n".join(rows)


def build_project_architecture_index(project_root: str | Path, *, max_modules: int = 1200) -> dict[str, Any]:
    """Index Python modules, imports, classes, functions and call sites without executing code."""
    root = Path(project_root).expanduser().resolve()
    warnings: list[str] = []
    files = _safe_python_files(root, warnings)[:max(1, min(int(max_modules), MAX_ANALYZED_FILES))]
    modules: list[dict[str, Any]] = []
    symbol_count = 0
    for relative, full_path in files:
        try:
            source = full_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            warnings.append(f"{relative}: индекс символов недоступен ({type(exc).__name__}).")
            continue
        imports: set[str] = set()
        symbols: list[dict[str, Any]] = []
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = "." * int(node.level) + str(node.module or "")
                imports.add(prefix)
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else (
                    "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                )
                signature = ast.get_source_segment(source, node) or ""
                signature = signature.splitlines()[0].strip()[:240]
                symbols.append({
                    "name": node.name,
                    "kind": kind,
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "end_line": int(getattr(node, "end_lineno", 0) or 0),
                    "signature": signature,
                })
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    calls.add(function.id)
                elif isinstance(function, ast.Attribute):
                    calls.add(function.attr)
        symbols.sort(key=lambda item: (item["line"], item["name"]))
        symbol_count += len(symbols)
        modules.append({
            "path": relative,
            "module": _module_name(relative),
            "is_test": relative.startswith("tests/") and PurePosixPath(relative).name.startswith("test_"),
            "imports": sorted(imports)[:80],
            "symbols": symbols[:160],
            "calls": sorted(calls)[:100],
        })
    return {
        "schema": 1,
        "analysis_kind": "static_python_ast_architecture_index",
        "module_count": len(modules),
        "symbol_count": symbol_count,
        "modules": modules,
        "warnings": sorted(set(warnings))[:40],
    }


def format_project_architecture_index(index: dict[str, Any], *, max_chars: int = 16000) -> str:
    """Format the project-wide symbol index for the user or a bounded model context."""
    limit = max(1000, int(max_chars))
    lines = [
        "КАРТА АРХИТЕКТУРЫ ПРОЕКТА (статический AST-анализ, код не исполнялся)",
        f"Python-модулей: {int(index.get('module_count', 0) or 0)}; классов/функций: {int(index.get('symbol_count', 0) or 0)}",
    ]
    used = sum(len(line) + 1 for line in lines)
    modules = index.get("modules", [])
    for module in modules if isinstance(modules, list) else []:
        if not isinstance(module, dict):
            continue
        symbols = module.get("symbols", [])
        names = [
            f"{item.get('kind')} {item.get('name')}() [стр. {item.get('line')}]"
            for item in symbols if isinstance(item, dict)
        ]
        entry = (
            f"\n{module.get('path')} — imports: {', '.join(module.get('imports', [])[:12]) or '—'}"
            f"\n  API: {'; '.join(names[:24]) or 'верхнеуровневые определения не найдены'}"
            f"\n  Вызовы: {', '.join(module.get('calls', [])[:24]) or '—'}"
        )
        if used + len(entry) > limit:
            lines.append("\n… индекс сокращён по лимиту контекста.")
            break
        lines.append(entry)
        used += len(entry)
    warnings = index.get("warnings", [])
    if warnings:
        lines.append("\nОграничения: " + " | ".join(str(item) for item in warnings[:8]))
    lines.append("\nВажно: AST показывает статические определения и вызовы, но не гарантирует обнаружение динамических импортов, reflection и runtime-связей.")
    return "\n".join(lines)


def _source_segment(source: str, node: ast.AST, limit: int = 240) -> str:
    try:
        value = ast.get_source_segment(source, node) or ""
    except (TypeError, ValueError):
        value = ""
    return value.splitlines()[0].strip()[:limit]


def build_function_call_graph(
    project_root: str | Path,
    target_relative_path: str | None = None,
    *,
    max_nodes: int = 4000,
    max_edges: int = 12000,
) -> dict[str, Any]:
    """Build a bounded static function/method call graph without importing project code.

    Resolved edges are evidence from AST call sites. Dynamic dispatch, reflection,
    callbacks and external APIs cannot be resolved completely and are reported separately.
    """
    root = Path(project_root).expanduser().resolve()
    warnings: list[str] = []
    files = _safe_python_files(root, warnings)
    target = str(target_relative_path or "").replace("\\", "/").strip()
    if target:
        pure = PurePosixPath(target)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("Для карты вызовов нужен относительный путь к Python-файлу.")
        target = pure.as_posix()

    path_to_module: dict[str, str] = {}
    module_to_path: dict[str, str] = {}
    for relative, _ in files:
        module = _module_name(relative)
        if module:
            path_to_module[relative] = module
            module_to_path.setdefault(module, relative)

    parsed: dict[str, tuple[str, ast.Module]] = {}
    symbols: dict[str, dict[str, Any]] = {}
    symbols_by_path: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    symbols_by_name: dict[str, list[str]] = defaultdict(list)

    def add_symbol(relative: str, source: str, node: ast.AST, qualname: str, kind: str) -> None:
        if len(symbols) >= max(1, min(int(max_nodes), 10000)):
            return
        name = str(getattr(node, "name", "") or "")
        if not name:
            return
        identifier = f"{relative}::{qualname}"
        symbols[identifier] = {
            "id": identifier,
            "path": relative,
            "name": name,
            "qualname": qualname,
            "kind": kind,
            "line": int(getattr(node, "lineno", 0) or 0),
            "end_line": int(getattr(node, "end_lineno", 0) or 0),
            "signature": _source_segment(source, node),
        }
        symbols_by_path[relative][name].append(identifier)
        symbols_by_name[name].append(identifier)

    for relative, full_path in files:
        try:
            source = full_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            warnings.append(f"{relative}: карта вызовов пропустила файл ({type(exc).__name__}).")
            continue
        parsed[relative] = (source, tree)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_symbol(relative, source, node, node.name, "function" if isinstance(node, ast.FunctionDef) else "async_function")
            elif isinstance(node, ast.ClassDef):
                add_symbol(relative, source, node, node.name, "class")
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        add_symbol(
                            relative, source, child, f"{node.name}.{child.name}",
                            "method" if isinstance(child, ast.FunctionDef) else "async_method",
                        )

    if target and target not in parsed:
        raise ValueError(f"Файл {target} не удалось включить в карту вызовов.")

    # Resolve imported names only when the import maps to a project module/symbol.
    aliases_by_path: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    for relative, (_source, tree) in parsed.items():
        current_module = path_to_module.get(relative, "")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_path = module_to_path.get(alias.name)
                    if imported_path:
                        aliases_by_path[relative][alias.asname or alias.name.split(".")[0]] = ("module", imported_path)
            elif isinstance(node, ast.ImportFrom):
                candidates = _resolve_import_candidates(
                    current_module, relative, node.module, node.level,
                    [alias.name for alias in node.names], module_to_path,
                )
                for alias in node.names:
                    for imported_path in candidates:
                        imported_symbol = f"{imported_path}::{alias.name}"
                        if imported_symbol in symbols:
                            aliases_by_path[relative][alias.asname or alias.name] = ("symbol", imported_symbol)
                            break
                        if alias.name == "*":
                            continue
                        # A from-import may import a submodule rather than a symbol.
                        submodule_path = module_to_path.get(f"{_module_name(imported_path) and _module_name(imported_path) + '.' or ''}{alias.name}")
                        if submodule_path:
                            aliases_by_path[relative][alias.asname or alias.name] = ("module", submodule_path)

    def call_targets(relative: str, current_class: str, call: ast.Call) -> list[str]:
        func = call.func
        local = symbols_by_path.get(relative, {})
        aliases = aliases_by_path.get(relative, {})
        if isinstance(func, ast.Name):
            local_matches = local.get(func.id, [])
            if len(local_matches) == 1 and symbols[local_matches[0]]["kind"] not in {"class"}:
                return local_matches
            alias = aliases.get(func.id)
            if alias:
                kind, value = alias
                if kind == "symbol" and value in symbols:
                    return [value]
            global_matches = symbols_by_name.get(func.id, [])
            if len(global_matches) == 1:
                return global_matches
            return []

        if isinstance(func, ast.Attribute):
            attr = func.attr
            base = func.value
            if isinstance(base, ast.Name) and base.id in {"self", "cls"} and current_class:
                candidate = f"{relative}::{current_class}.{attr}"
                return [candidate] if candidate in symbols else []
            if isinstance(base, ast.Name) and base.id in aliases:
                kind, value = aliases[base.id]
                candidate = f"{value}::{attr}" if kind == "module" else f"{value}.{attr}"
                if candidate in symbols:
                    return [candidate]
                # Imported class methods are represented as File.py::Class.method.
                if kind == "symbol":
                    candidate = f"{value}.{attr}"
                    if candidate in symbols:
                        return [candidate]
            # Resolve a class-local explicit call such as Worker.run(...).
            if isinstance(base, ast.Name):
                candidate = f"{relative}::{base.id}.{attr}"
                if candidate in symbols:
                    return [candidate]
            same_file = local.get(attr, [])
            if len(same_file) == 1:
                return same_file
        return []

    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    adjacency: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)

    def calls_in_scope(function: ast.AST):
        pending = list(reversed(list(getattr(function, "body", []))))
        while pending:
            current = pending.pop()
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(current, ast.Call):
                yield current
            pending.extend(reversed(list(ast.iter_child_nodes(current))))

    for identifier, meta in symbols.items():
        if meta["kind"] == "class":
            continue
        relative = str(meta["path"])
        source, tree = parsed[relative]
        # Find the exact function/method node by its recorded source line.
        owner_class = str(meta["qualname"]).rsplit(".", 1)[0] if "." in str(meta["qualname"]) else ""
        function_node = None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not owner_class and node.lineno == meta["line"]:
                function_node = node
                break
            if isinstance(node, ast.ClassDef) and owner_class == node.name:
                function_node = next((
                    child for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.lineno == meta["line"]
                ), None)
                break
        if function_node is None:
            continue
        for call in calls_in_scope(function_node):
            targets = call_targets(relative, owner_class, call)
            if targets:
                for destination in targets:
                    if len(edges) >= max(1, min(int(max_edges), 30000)):
                        warnings.append(f"Достигнут предел карты вызовов: {max_edges} рёбер.")
                        break
                    edge = {"from": identifier, "to": destination, "line": int(getattr(call, "lineno", 0) or 0)}
                    edges.append(edge)
                    adjacency[identifier].add(destination)
                    reverse[destination].add(identifier)
            else:
                func = call.func
                call_name = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else type(func).__name__
                )
                dynamic = (
                    call_name in {"getattr", "setattr", "eval", "exec", "compile", "__import__"}
                    or (isinstance(func, ast.Attribute) and func.attr in {"import_module", "run_module"})
                    or (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in {"self", "cls"})
                )
                if dynamic and (not target or relative == target) and len(unresolved) < 200:
                    unresolved.append({
                        "caller": identifier,
                        "path": relative,
                        "line": int(getattr(call, "lineno", 0) or 0),
                        "call": _source_segment(source, call, 180),
                        "reason": "dynamic_or_unresolved_dispatch",
                    })

    target_ids = {
        identifier for identifier, meta in symbols.items()
        if not target or meta["path"] == target
    }
    target_callers = sorted({
        caller for identifier in target_ids for caller in reverse.get(identifier, set())
        if caller not in target_ids
    })
    target_callees = sorted({
        destination for identifier in target_ids for destination in adjacency.get(identifier, set())
        if destination not in target_ids
    })
    functions = [
        symbols[identifier] for identifier in sorted(target_ids)
        if symbols[identifier]["kind"] != "class"
    ]
    return {
        "target": target or None,
        "node_count": len(symbols),
        "edge_count": len(edges),
        "functions": functions[:500],
        "direct_callers": [symbols[item] for item in target_callers[:100] if item in symbols],
        "direct_callees": [symbols[item] for item in target_callees[:100] if item in symbols],
        "unresolved_calls": unresolved,
        "warnings": sorted(set(warnings))[:40],
        "analysis_kind": "static_ast_function_call_graph",
    }


def analyze_function_data_flow(
    project_root: str | Path,
    target_relative_path: str,
    *,
    max_functions: int = 120,
) -> dict[str, Any]:
    """Summarize function inputs, reads, writes, returns and likely side effects.

    This is a conservative AST approximation, not runtime taint tracking.
    """
    root = Path(project_root).expanduser().resolve()
    relative = str(target_relative_path).replace("\\", "/").strip()
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("Для анализа данных нужен относительный путь к Python-модулю.")
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise ValueError(f"Модуль {relative} отсутствует или находится вне проекта.")
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"Не удалось разобрать поток данных {relative}: {type(exc).__name__}.") from exc

    summaries: list[dict[str, Any]] = []
    warnings: list[str] = []

    class FlowVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.reads: set[str] = set()
            self.writes: set[str] = set()
            self.global_names: set[str] = set()
            self.returns: list[str] = []
            self.calls: list[str] = []
            self.side_effects: set[str] = set()
            self.dynamic: set[str] = set()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Load):
                self.reads.add(node.id)
            elif isinstance(node.ctx, (ast.Store, ast.Del)):
                self.writes.add(node.id)

        def visit_Global(self, node: ast.Global) -> None:
            self.global_names.update(node.names)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                try:
                    self.writes.add(ast.unparse(node)[:120])
                except Exception:
                    self.writes.add(node.attr)
            self.generic_visit(node)

        def visit_Return(self, node: ast.Return) -> None:
            if node.value is not None and len(self.returns) < 12:
                try:
                    self.returns.append(ast.unparse(node.value)[:180])
                except Exception:
                    self.returns.append(type(node.value).__name__)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            try:
                call_text = ast.unparse(node.func)[:160]
            except Exception:
                call_text = type(node.func).__name__
            if len(self.calls) < 40:
                self.calls.append(call_text)
            lowered = call_text.casefold()
            if any(token in lowered for token in ("open", "read_text", "write_text", "read_bytes", "write_bytes", "mkdir", "unlink", "replace", "copy", "move", "rmtree")):
                self.side_effects.add("file_system")
            if any(token in lowered for token in ("requests.", "urllib.", "http.", "socket.", "urlopen", "fetch", "post", "get")):
                self.side_effects.add("network")
            if any(token in lowered for token in ("sqlite", "execute", "commit", "rollback", "cursor", "connect")):
                self.side_effects.add("database")
            if any(token in lowered for token in ("subprocess", "popen", "system", "create_subprocess")):
                self.side_effects.add("process_execution")
            if any(token in lowered for token in ("thread", "queue", "asyncio", "create_task", "executor")):
                self.side_effects.add("concurrency")
            if any(token in lowered for token in ("tkinter", "messagebox", "ttk.", ".configure", ".insert", ".delete")):
                self.side_effects.add("user_interface")
            if any(token in lowered for token in ("getattr", "setattr", "eval", "exec", "import_module", "__import__")):
                self.dynamic.add(call_text)
            self.generic_visit(node)

    def add_function(node: ast.AST, owner: str = "") -> None:
        if len(summaries) >= max(1, min(int(max_functions), 500)):
            return
        visitor = FlowVisitor()
        for statement in getattr(node, "body", []):
            visitor.visit(statement)
        args = getattr(node, "args", None)
        parameters = []
        if args is not None:
            parameters = [
                argument.arg for argument in (
                    list(getattr(args, "posonlyargs", []))
                    + list(getattr(args, "args", []))
                    + list(getattr(args, "kwonlyargs", []))
                )
                if argument.arg not in {"self", "cls"}
            ]
            if args.vararg:
                parameters.append("*" + args.vararg.arg)
            if args.kwarg:
                parameters.append("**" + args.kwarg.arg)
        name = str(getattr(node, "name", ""))
        summaries.append({
            "name": f"{owner}.{name}" if owner else name,
            "line": int(getattr(node, "lineno", 0) or 0),
            "parameters": parameters[:40],
            "reads": sorted(visitor.reads - set(parameters))[:50],
            "writes": sorted(visitor.writes)[:50],
            "global_writes": sorted(visitor.global_names.intersection(visitor.writes))[:30],
            "returns": visitor.returns,
            "calls": sorted(set(visitor.calls))[:40],
            "side_effects": sorted(visitor.side_effects),
            "dynamic_operations": sorted(visitor.dynamic)[:15],
        })

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_function(node)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_function(child, node.name)
    if len(summaries) >= max(1, min(int(max_functions), 500)):
        warnings.append(f"Перечень функций ограничен значением {max_functions}.")
    if not summaries:
        warnings.append("На верхнем уровне модуля не найдены функции или методы.")
    if any(item["dynamic_operations"] for item in summaries):
        warnings.append("Обнаружены динамические операции; фактическое движение данных может отличаться от статической оценки.")
    return {
        "target": pure.as_posix(),
        "functions": summaries,
        "warnings": warnings,
        "analysis_kind": "static_ast_data_flow_approximation",
    }


def assess_architecture_change_impact(
    dependency_analysis: dict[str, Any],
    call_graph: dict[str, Any],
    data_flow: dict[str, Any],
) -> dict[str, Any]:
    """Estimate change risk from affected modules, callers, side effects and unknown edges."""
    dependents = dependency_analysis.get("transitive_dependents", [])
    tests = dependency_analysis.get("affected_tests", [])
    callers = call_graph.get("direct_callers", [])
    unresolved = call_graph.get("unresolved_calls", [])
    warnings = list(dependency_analysis.get("warnings", [])) + list(call_graph.get("warnings", [])) + list(data_flow.get("warnings", []))
    side_effects = sorted({
        effect
        for function in data_flow.get("functions", [])
        if isinstance(function, dict)
        for effect in function.get("side_effects", [])
    })
    reasons: list[str] = []
    score = 0
    if len(dependents) >= 8:
        score += 2
        reasons.append(f"много косвенно зависящих модулей: {len(dependents)}")
    elif len(dependents) >= 3:
        score += 1
        reasons.append(f"несколько зависящих модулей: {len(dependents)}")
    if len(callers) >= 6:
        score += 2
        reasons.append(f"много обнаруженных вызывающих функций: {len(callers)}")
    elif callers:
        score += 1
        reasons.append(f"обнаружены вызывающие функции: {len(callers)}")
    if unresolved:
        score += 2
        reasons.append(f"не удалось разрешить часть динамических/неоднозначных вызовов: {len(unresolved)}")
    if side_effects:
        score += 1
        reasons.append("изменяемый модуль имеет побочные эффекты: " + ", ".join(side_effects))
    if not tests:
        score += 1
        reasons.append("автоматические связанные тесты статически не обнаружены")
    if warnings:
        score += 1
        reasons.append("анализ содержит предупреждения или неполные данные")
    level = "high" if score >= 5 else "medium" if score >= 2 else "low"
    return {
        "risk_level": level,
        "risk_score_heuristic": score,
        "reasons": reasons or ["значимые факторы риска статическим анализом не обнаружены"],
        "affected_modules": len(dependents) + 1,
        "affected_tests": len(tests),
        "unresolved_calls": len(unresolved),
        "side_effects": side_effects,
        "confidence": "limited_static_analysis",
    }


def build_architecture_intelligence_context(
    project_root: str | Path,
    target_relative_path: str,
    *,
    max_chars: int = 6500,
) -> str:
    """Create bounded call-flow, data-flow, impact and uncertainty context for a coding model."""
    root = Path(project_root).expanduser().resolve()
    relative = str(target_relative_path).replace("\\", "/").strip()
    dependency = analyze_module_dependencies(root, relative)
    graph = build_function_call_graph(root, relative)
    flow = analyze_function_data_flow(root, relative)
    impact = assess_architecture_change_impact(dependency, graph, flow)

    lines = [
        "ГЛУБОКИЙ АРХИТЕКТУРНЫЙ КОНТЕКСТ (статический анализ, исходный код не исполнялся)",
        f"Целевой модуль: {relative}",
        f"Оценка риска изменения: {impact['risk_level']} (эвристика, не гарантия безопасности)",
        "Факторы риска: " + "; ".join(impact["reasons"][:8]),
    ]
    callers = graph.get("direct_callers", [])
    lines.append("Найденные вызывающие функции: " + (
        "; ".join(f"{row.get('path')}::{row.get('qualname')} [стр. {row.get('line')}]" for row in callers[:18])
        if callers else "не обнаружены статическим поиском"
    ))
    callees = graph.get("direct_callees", [])
    lines.append("Внешние для выбранного файла вызываемые функции: " + (
        "; ".join(f"{row.get('path')}::{row.get('qualname')}" for row in callees[:18])
        if callees else "не обнаружены статическим поиском"
    ))
    for function in flow.get("functions", [])[:35]:
        if not isinstance(function, dict):
            continue
        effects = ", ".join(function.get("side_effects", [])) or "не выявлены"
        parameters = ", ".join(function.get("parameters", [])) or "нет явных параметров"
        writes = ", ".join(function.get("writes", [])[:12]) or "не выявлены"
        returns = "; ".join(function.get("returns", [])[:4]) or "явный return не обнаружен"
        lines.append(
            f"Поток {function.get('name')} [стр. {function.get('line')}]: "
            f"входы=({parameters}); записи=({writes}); возврат=({returns}); побочные эффекты=({effects})"
        )
    unknowns = graph.get("unresolved_calls", [])
    if unknowns:
        lines.append("НЕРАЗРЕШЁННЫЕ ВЫЗОВЫ: " + "; ".join(
            f"{item.get('path')}:{item.get('line')} {item.get('call')}" for item in unknowns[:12]
        ))
    warnings = list(dependency.get("warnings", [])) + list(graph.get("warnings", [])) + list(flow.get("warnings", []))
    warnings = list(dict.fromkeys(str(item) for item in warnings if item))
    lines.append("ПРОБЕЛЫ И НЕОПРЕДЕЛЁННОСТЬ: " + (
        " | ".join(warnings[:10]) if warnings else "явных предупреждений статического анализа нет"
    ))
    lines.append(
        "ОГРАНИЧЕНИЕ: карта импортов, вызовов и потоков данных неполная для reflection, "
        "динамических импортов, callback, monkey-patching и runtime-зависимостей. "
        "Не делай вывод о безопасности или отсутствии влияния только по отсутствию ребра."
    )
    result = "\n".join(lines)
    limit = max(1200, int(max_chars))
    return result if len(result) <= limit else result[:limit - 100] + "\n… архитектурный контекст сокращён по лимиту."



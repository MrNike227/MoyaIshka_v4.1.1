# -*- coding: utf-8 -*-
"""Safe, allow-listed Windows app and folder launcher for Моя ИИшка."""
from __future__ import annotations

# Standard library
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActionResult:
    handled: bool
    success: bool
    message: str


APP_COMMANDS: dict[str, tuple[str, ...]] = {
    "блокнот": ("notepad.exe",),
    "notepad": ("notepad.exe",),
    "калькулятор": ("calc.exe",),
    "кальк": ("calc.exe",),
    "проводник": ("explorer.exe",),
    "explorer": ("explorer.exe",),
    "paint": ("mspaint.exe",),
    "паинт": ("mspaint.exe",),
    "диспетчер задач": ("taskmgr.exe",),
    "панель управления": ("control.exe",),
    "редактор реестра": ("regedit.exe",),
    "настройки": ("ms-settings:",),
    "параметры": ("ms-settings:",),
}

FOLDER_ALIASES = {
    "рабочий стол": "Desktop",
    "десктоп": "Desktop",
    "загрузки": "Downloads",
    "скачивания": "Downloads",
    "документы": "Documents",
    "изображения": "Pictures",
    "картинки": "Pictures",
    "музыка": "Music",
    "видео": "Videos",
    "домашнюю": ".",
    "домой": ".",
}


def launch_app(app_name: str) -> ActionResult:
    key = app_name.strip().lower()
    command = APP_COMMANDS.get(key)
    if not command:
        return ActionResult(True, False, f"Приложение «{app_name}» не входит в список разрешённых. Открой его вручную или добавь безопасный ярлык в настройки.")
    try:
        if command[0].endswith(":") and os.name == "nt":
            os.startfile(command[0])  # type: ignore[attr-defined]
        elif os.name == "nt":
            subprocess.Popen(list(command), shell=False)
        else:
            return ActionResult(True, False, "Управление приложениями доступно только в Windows.")
        return ActionResult(True, True, f"Открываю: {app_name}.")
    except Exception as exc:
        return ActionResult(True, False, f"Не удалось открыть {app_name}: {exc}")


def open_known_folder(folder_name: str) -> ActionResult:
    key = re.sub(r"\s+", " ", folder_name.strip().lower())
    folder = FOLDER_ALIASES.get(key)
    if not folder:
        return ActionResult(True, False, "Я могу открыть только стандартные папки: Рабочий стол, Загрузки, Документы, Изображения, Музыка, Видео или домашнюю папку.")
    path = Path.home() if folder == "." else Path.home() / folder
    if not path.exists():
        # Windows localized folder names may differ; use the known-folder path from shell if available.
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                # CSIDL values: Desktop=0x10, Personal=0x05, MyPictures=0x27, MyMusic=0x0d, MyVideo=0x0e.
                csidl = {"Desktop": 0x10, "Documents": 0x05, "Pictures": 0x27, "Music": 0x0d, "Videos": 0x0e}.get(folder)
                if csidl is not None:
                    buffer = ctypes.create_unicode_buffer(260)
                    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) == 0:
                        path = Path(buffer.value)
            except Exception:
                pass
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            return ActionResult(True, False, "Открытие папок через помощника доступно в Windows.")
        return ActionResult(True, True, f"Открываю папку: {path}")
    except Exception as exc:
        return ActionResult(True, False, f"Не удалось открыть папку: {exc}")


def handle_voice_command(text: str) -> ActionResult:
    """Only handles explicit safe phrases; never evaluates arbitrary shell text."""
    value = re.sub(r"\s+", " ", text.strip().lower())
    value = re.sub(r"[.!?]+$", "", value)
    if not value:
        return ActionResult(False, False, "")
    match = re.fullmatch(r"(?:открой|запусти|открывай)\s+(?:программу\s+)?(.+)", value)
    if match:
        target = match.group(1).strip()
        folder_match = re.fullmatch(r"(?:папку\s+)?(.+)", target)
        candidate = folder_match.group(1) if folder_match else target
        if candidate in FOLDER_ALIASES:
            return open_known_folder(candidate)
        if candidate in APP_COMMANDS:
            return launch_app(candidate)
        if target.startswith("папку "):
            return open_known_folder(target[len("папку "):].strip())
        # Do not interpret unrecognized text as a shell command.
        return ActionResult(True, False, f"Команда «{target}» не входит в безопасный список. Доступные программы: блокнот, калькулятор, проводник, Paint, диспетчер задач, панель управления, настройки.")
    match = re.fullmatch(r"(?:открой|покажи)\s+папку\s+(.+)", value)
    if match:
        return open_known_folder(match.group(1))
    return ActionResult(False, False, "")

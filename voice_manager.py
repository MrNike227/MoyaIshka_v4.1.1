# -*- coding: utf-8 -*-
"""Download and manage local Piper TTS voice packs.

Voice models are downloaded on demand into the user's ISH data directory.
Each model is pinned to the upstream piper-voices v1.0.0 release and verified
with SHA-256 before it can be selected. Voice configs are parsed and checked.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
MAX_MODEL_BYTES = 100 * 1024 * 1024
MAX_CONFIG_BYTES = 1024 * 1024

# SHA-256 values are from the pinned Hugging Face model files.
VOICE_CATALOG: dict[str, dict[str, Any]] = {
    "ru_RU-irina-medium": {
        "name": "Ирина",
        "language": "ru_RU",
        "quality": "medium",
        "size_bytes": 63201294,
        "relative_model": "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx",
        "sha256": "8ff38212d23da300bbe3705c645e6e5b9475f0bfde01558eb17813e22acaaaaa",
        "license": "MIT (репозиторий моделей Piper)",
    },
    "ru_RU-denis-medium": {
        "name": "Денис",
        "language": "ru_RU",
        "quality": "medium",
        "size_bytes": 63221984,
        "relative_model": "ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx",
        "sha256": "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a",
        "license": "MIT (репозиторий моделей Piper)",
    },
    "ru_RU-dmitri-medium": {
        "name": "Дмитрий",
        "language": "ru_RU",
        "quality": "medium",
        "size_bytes": 63201294,
        "relative_model": "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx",
        "sha256": "f073356ebc4bd0f80c5af58df2953a5988bd5bdab1eb38635ce960b071fbefcb",
        "license": "MIT (репозиторий моделей Piper)",
    },
    "ru_RU-ruslan-medium": {
        "name": "Руслан",
        "language": "ru_RU",
        "quality": "medium",
        "size_bytes": 63201294,
        "relative_model": "ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx",
        "sha256": "72a5f88e0b20928064eb45d88e1daa21f8af62d18613580d32cbb4aed48dcf7f",
        "license": "MIT (репозиторий моделей Piper)",
    },
}


def voice_directory(data_dir: str | Path) -> Path:
    directory = Path(data_dir).expanduser() / "voices" / "piper"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def voice_paths(data_dir: str | Path, voice_id: str) -> tuple[Path, Path]:
    item = VOICE_CATALOG.get(voice_id)
    if not item:
        raise ValueError("Неизвестный голос. Выбери голос из встроенного каталога.")
    model_name = Path(str(item["relative_model"])).name
    directory = voice_directory(data_dir)
    return directory / model_name, directory / (model_name + ".json")


def is_voice_installed(data_dir: str | Path, voice_id: str) -> bool:
    try:
        model_path, config_path = voice_paths(data_dir, voice_id)
        if not model_path.is_file() or not config_path.is_file():
            return False
        config = json.loads(config_path.read_text(encoding="utf-8"))
        language_code = str(config.get("language", {}).get("code", ""))
        return language_code == str(VOICE_CATALOG[voice_id]["language"]) and model_path.stat().st_size > 1_000_000
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return False


def installed_voice_ids(data_dir: str | Path) -> list[str]:
    return [voice_id for voice_id in VOICE_CATALOG if is_voice_installed(data_dir, voice_id)]


def _download_to_file(
    url: str,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    max_bytes: int = MAX_CONFIG_BYTES,
    progress: Callable[[int, int], None] | None = None,
    progress_offset: int = 0,
    progress_total: int = 1,
) -> int:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ISH-VoiceManager/4.1.5.1", "Accept": "application/octet-stream"},
    )
    temporary = destination.with_name(destination.name + ".part")
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as stream:
            header_length = response.headers.get("Content-Length")
            expected_length = int(header_length) if header_length and header_length.isdigit() else 0
            if expected_length > max_bytes:
                raise ValueError("Файл голоса превышает допустимый размер загрузки.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError("Загружаемый файл превысил допустимый размер.")
                stream.write(chunk)
                digest.update(chunk)
                if progress:
                    current = progress_offset + downloaded
                    progress(current, progress_total)
        if downloaded == 0:
            raise RuntimeError("Сервер вернул пустой файл голоса.")
        if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
            raise RuntimeError("SHA-256 голосовой модели не совпал. Файл удалён, голос не установлен.")
        temporary.replace(destination)
        return downloaded
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def download_voice(
    data_dir: str | Path,
    voice_id: str,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Download a pinned voice model + JSON config and verify before install."""
    item = VOICE_CATALOG.get(voice_id)
    if not item:
        raise ValueError("Выбранного голоса нет во встроенном каталоге.")
    model_path, config_path = voice_paths(data_dir, voice_id)
    model_url = f"{REPOSITORY}/{item['relative_model']}"
    config_url = model_url + ".json"
    expected_size = int(item["size_bytes"])
    total = expected_size + 16_384
    _download_to_file(
        model_url,
        model_path,
        expected_sha256=str(item["sha256"]),
        max_bytes=MAX_MODEL_BYTES,
        progress=progress,
        progress_offset=0,
        progress_total=total,
    )
    try:
        _download_to_file(
            config_url,
            config_path,
            max_bytes=MAX_CONFIG_BYTES,
            progress=progress,
            progress_offset=expected_size,
            progress_total=total,
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        language_code = str(config.get("language", {}).get("code", ""))
        sample_rate = int(config.get("audio", {}).get("sample_rate", 0))
        if language_code != str(item["language"]):
            raise RuntimeError("Конфигурация голоса не соответствует выбранному языку.")
        if not 8000 <= sample_rate <= 48000:
            raise RuntimeError("Конфигурация голоса содержит неверную частоту дискретизации.")
        if not is_voice_installed(data_dir, voice_id):
            raise RuntimeError("Файлы голоса загружены, но не прошли итоговую проверку.")
        if progress:
            progress(total, total)
        return model_path, config_path
    except Exception:
        model_path.unlink(missing_ok=True)
        config_path.unlink(missing_ok=True)
        raise


def delete_voice(data_dir: str | Path, voice_id: str) -> None:
    model_path, config_path = voice_paths(data_dir, voice_id)
    model_path.unlink(missing_ok=True)
    config_path.unlink(missing_ok=True)


def voice_label(voice_id: str) -> str:
    item = VOICE_CATALOG[voice_id]
    return f"{item['name']} · Русский · {item['quality']} · около 60 МБ"

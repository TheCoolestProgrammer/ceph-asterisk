"""Общая библиотека пользовательских звуков (asterisk_configs/sounds)."""

from __future__ import annotations

import wave
from datetime import date
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audio_files import AudioFile, AudioFormat
from app.utils.instance_volumes import shared_sounds_writable_dir

SUPPORTED_EXTENSIONS = {f.value for f in AudioFormat}

AUDIO_MEDIA_TYPES = {
    "wav": "audio/wav",
    "gsm": "audio/gsm",
    "ulaw": "audio/basic",
    "alaw": "audio/basic",
    "mp3": "audio/mpeg",
}


def resolve_shared_sound_path(name: str, fmt: str | None = None) -> Path | None:
    """
    Ищет файл в общей библиотеке без учёта регистра расширения.

    На Linux file.wav и file.WAV — разные имена, но один формат.
    """
    sounds_dir = Path(shared_sounds_writable_dir())
    if not sounds_dir.is_dir():
        return None

    normalized_name = name.lower()
    normalized_fmt = fmt.lower() if fmt else None

    if normalized_fmt:
        exact = sounds_dir / f"{name}.{fmt}"
        if exact.is_file():
            return exact

    for entry in sounds_dir.iterdir():
        if not entry.is_file():
            continue
        suffix = entry.suffix.lstrip(".").lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            continue
        if entry.stem.lower() != normalized_name:
            continue
        if normalized_fmt and suffix != normalized_fmt:
            continue
        return entry
    return None


def scan_shared_sound_files() -> list[Path]:
    sounds_dir = Path(shared_sounds_writable_dir())
    if not sounds_dir.is_dir():
        return []
    return sorted(
        (
            entry
            for entry in sounds_dir.iterdir()
            if entry.is_file()
            and entry.suffix.lstrip(".").lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )


def _wav_duration_sec(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as wav_file:
            return int(wav_file.getnframes() / float(wav_file.getframerate()))
    except (wave.Error, OSError):
        return 0


def sync_disk_library_to_db(db: Session) -> None:
    """Регистрирует в БД файлы из sounds/, добавленные вручную или с другим регистром."""
    changed = False
    for path in scan_shared_sound_files():
        name = path.stem
        fmt = path.suffix.lstrip(".").lower()
        existing = (
            db.query(AudioFile)
            .filter(func.lower(AudioFile.name) == name.lower())
            .first()
        )
        if existing:
            if existing.format != fmt:
                existing.format = fmt
                changed = True
            continue

        db.add(
            AudioFile(
                name=name,
                format=fmt,
                size_kb=path.stat().st_size / 1024,
                duration_sec=_wav_duration_sec(path) if fmt == "wav" else 0,
                create_date=date.today(),
            )
        )
        changed = True

    if changed:
        db.commit()


def library_media_type(fmt: str) -> str:
    return AUDIO_MEDIA_TYPES.get(fmt.lower(), f"audio/{fmt.lower()}")

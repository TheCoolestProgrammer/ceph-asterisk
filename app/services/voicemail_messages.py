"""Сканирование записей app_voicemail на диске (INBOX и др.)."""

from __future__ import annotations

import configparser
import os
import re
from datetime import date, datetime
from pathlib import Path

from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_voicemail_spool import instance_voicemail_host_dir

AUDIO_EXTENSIONS = {".wav", ".WAV", ".gsm", ".GSM", ".ulaw", ".alaw", ".sln", ".sln16"}
# Один voicemail-message может иметь несколько файлов (wav+gsm); отдаём один формат.
PREFERRED_AUDIO_EXTENSIONS = (".wav", ".gsm", ".ulaw", ".alaw", ".sln", ".sln16")
VM_FOLDERS = ("INBOX", "Old", "Urgent", "Work", "Family", "Friends")


def _audio_format_rank(suffix: str) -> int:
    normalized = suffix.lower()
    for index, ext in enumerate(PREFERRED_AUDIO_EXTENSIONS):
        if normalized == ext:
            return index
    return len(PREFERRED_AUDIO_EXTENSIONS)


def _pick_preferred_audio_file(candidates: list[Path]) -> Path:
    return min(candidates, key=lambda path: _audio_format_rank(path.suffix))


def _parse_vm_txt(txt_path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    if not txt_path.is_file():
        return meta
    parser = configparser.ConfigParser()
    text = ""
    try:
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        parser.read_string(text)
        if parser.has_section("message"):
            meta = {k: v for k, v in parser.items("message")}
    except (OSError, configparser.Error):
        pass
    if not meta:
        try:
            if not text:
                text = txt_path.read_text(encoding="utf-8", errors="replace")
            for key in ("callerid", "origdate", "duration", "origtime"):
                match = re.search(rf"^{key}=(.+)$", text, re.MULTILINE | re.IGNORECASE)
                if match:
                    meta[key] = match.group(1).strip()
        except OSError:
            pass
    return meta


def _message_date(meta: dict[str, str], audio_path: Path) -> date:
    if "origtime" in meta:
        try:
            return datetime.fromtimestamp(int(meta["origtime"])).date()
        except (TypeError, ValueError, OSError):
            pass
    try:
        return datetime.fromtimestamp(audio_path.stat().st_mtime).date()
    except OSError:
        return date.today()


def _vm_entry_id(instance_id: int, rel_path: str) -> str:
    return f"vm:{instance_id}:{rel_path}"


def list_voicemail_recordings(
    instance: AsteriskInstance,
    *,
    instance_id: int,
    mailbox: str | None = None,
    context: str = "default",
) -> list[dict]:
    """
    Список записей для API /audio_files.
    rel_path относительно каталога voicemail на хосте, например default/101/INBOX/msg0000.WAV
    """
    root = Path(instance_voicemail_host_dir(instance))
    if not root.is_dir():
        return []

    context_dir = root / context
    if not context_dir.is_dir():
        return []

    mailboxes = [mailbox] if mailbox else sorted(
        p.name for p in context_dir.iterdir() if p.is_dir()
    )

    items: list[dict] = []
    for box in mailboxes:
        box_dir = context_dir / box
        if not box_dir.is_dir():
            continue
        for folder in VM_FOLDERS:
            folder_dir = box_dir / folder
            if not folder_dir.is_dir():
                continue
            by_message: dict[str, list[Path]] = {}
            for audio_path in folder_dir.iterdir():
                if not audio_path.is_file():
                    continue
                if audio_path.suffix not in AUDIO_EXTENSIONS:
                    continue
                message_key = audio_path.stem.lower()
                by_message.setdefault(message_key, []).append(audio_path)

            for audio_path in (
                _pick_preferred_audio_file(paths) for paths in by_message.values()
            ):
                rel = audio_path.relative_to(root).as_posix()
                txt_path = audio_path.with_suffix(".txt")
                meta = _parse_vm_txt(txt_path)
                try:
                    size_kb = audio_path.stat().st_size / 1024
                except OSError:
                    size_kb = 0.0
                duration_raw = meta.get("duration", "0")
                try:
                    duration_sec = int(float(duration_raw))
                except (TypeError, ValueError):
                    duration_sec = 0
                caller = meta.get("callerid", "")
                items.append(
                    {
                        "id": _vm_entry_id(instance_id, rel),
                        "name": f"{box}/{folder}/{audio_path.name}",
                        "format": audio_path.suffix.lstrip(".").lower(),
                        "size_kb": round(size_kb, 2),
                        "duration_sec": duration_sec,
                        "create_date": _message_date(meta, audio_path),
                        "source": "voicemail",
                        "instance_id": instance_id,
                        "instance_name": instance.name,
                        "mailbox": box,
                        "folder": folder,
                        "caller_id": caller,
                        "vm_path": rel,
                    }
                )

    items.sort(key=lambda x: (x["create_date"], x["name"]), reverse=True)
    return items


def resolve_voicemail_message_file(
    instance: AsteriskInstance,
    *,
    context: str,
    mailbox: str,
    folder: str,
    filename: str,
) -> Path:
    """
    Ищет аудиофайл сообщения в папке ящика.
    filename может быть msg0000.wav — подберётся существующий формат (wav/gsm).
    """
    root = Path(instance_voicemail_host_dir(instance)).resolve()
    folder_dir = root / context / mailbox / folder
    if not folder_dir.is_dir():
        raise FileNotFoundError(f"{context}/{mailbox}/{folder}")

    requested = Path(filename)
    stem = requested.stem.lower()
    candidates = [
        path
        for path in folder_dir.iterdir()
        if path.is_file()
        and path.suffix in AUDIO_EXTENSIONS
        and path.stem.lower() == stem
    ]
    if not candidates:
        raise FileNotFoundError(filename)

    return _pick_preferred_audio_file(candidates)


def resolve_voicemail_audio_path(
    instance: AsteriskInstance,
    rel_path: str,
) -> Path:
    root = Path(instance_voicemail_host_dir(instance)).resolve()
    full = (root / rel_path).resolve()
    if not str(full).startswith(str(root)):
        raise ValueError("Invalid voicemail path")
    if not full.is_file():
        raise FileNotFoundError(rel_path)
    if full.suffix not in AUDIO_EXTENSIONS:
        raise ValueError("Not an audio file")
    return full


def parse_voicemail_entry_id(entry_id: str) -> tuple[int, str] | None:
    """vm:{instance_id}:{rel_path}"""
    if not entry_id.startswith("vm:"):
        return None
    parts = entry_id.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        inst_id = int(parts[1])
    except ValueError:
        return None
    return inst_id, parts[2]

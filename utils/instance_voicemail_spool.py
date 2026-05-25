"""Каталог голосовых сообщений на хосте (bind-mount в Asterisk)."""

import os

from config import config
from models.asterisk_instance import AsteriskInstance
from utils.instance_paths import docker_volume_config_dir, writable_config_dir

VOICEMAIL_SUBDIR = "voicemail"
ASTERISK_VM_CONTAINER_PATH = "/var/spool/asterisk/voicemail"
VM_CONTEXT_NAME = "default"
VM_MAILBOX_FOLDERS = ("INBOX", "Old", "Urgent", "Work", "Family", "Friends")


def instance_voicemail_host_dir(instance: AsteriskInstance) -> str:
    """Путь для API (чтение файлов с диска)."""
    return os.path.join(writable_config_dir(instance), VOICEMAIL_SUBDIR)


def instance_voicemail_docker_dir(instance: AsteriskInstance) -> str:
    """Путь на хосте для docker volume."""
    return os.path.join(docker_volume_config_dir(instance), VOICEMAIL_SUBDIR)


def _chown_tree(path: str, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except OSError:
        pass
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                os.chown(os.path.join(root, name), uid, gid)
            except OSError:
                pass


def ensure_instance_voicemail_dir(
    instance: AsteriskInstance,
    mailboxes: list[str] | None = None,
    *,
    context: str = VM_CONTEXT_NAME,
) -> str:
    """
    {config}/voicemail → /var/spool/asterisk/voicemail.
    Создаёт default/{mailbox}/INBOX и выставляет владельца asterisk (UID из .env).
    """
    path = instance_voicemail_docker_dir(instance)
    os.makedirs(path, exist_ok=True)

    boxes = mailboxes or ["101", "102"]
    for box in boxes:
        for folder in VM_MAILBOX_FOLDERS:
            os.makedirs(os.path.join(path, context, box, folder), exist_ok=True)

    uid, gid = config.ASTERISK_UID, config.ASTERISK_GID
    _chown_tree(path, uid, gid)
    try:
        os.chmod(path, 0o775)
    except OSError:
        pass

    api_path = instance_voicemail_host_dir(instance)
    if api_path != path:
        if not os.path.isdir(api_path):
            os.makedirs(api_path, exist_ok=True)
        for box in boxes:
            for folder in VM_MAILBOX_FOLDERS:
                dest = os.path.join(api_path, context, box, folder)
                os.makedirs(dest, exist_ok=True)
        _chown_tree(api_path, uid, gid)

    return path


def warn_if_empty_sounds_dir(instance: AsteriskInstance) -> str | None:
    """Пустой sounds/ не монтируется, но непустой без vm-* ломает промпты."""
    base = docker_volume_config_dir(instance)
    sounds_path = os.path.join(base, "sounds")
    if not os.path.isdir(sounds_path):
        return None
    try:
        entries = list(os.scandir(sounds_path))
    except OSError:
        return None
    if not entries:
        return (
            "Каталог sounds/ пуст — удалите его, иначе после добавления файлов "
            "он может перекрыть vm-intro в контейнере."
        )
    if not any(e.name.startswith("vm-intro") for e in entries if e.is_file()):
        return (
            "Каталог sounds/ смонтирован поверх промптов Asterisk, но vm-intro "
            "в нём нет — голосовая почта может сразу обрывать вызов."
        )
    return None

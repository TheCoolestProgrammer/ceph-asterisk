"""Каталог голосовых сообщений на хосте (bind-mount в Asterisk)."""

import os

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import docker_volume_config_dir, writable_config_dir

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


def ensure_mailbox_voicemail_dir(
    instance: AsteriskInstance,
    mailbox: str,
    *,
    context: str = VM_CONTEXT_NAME,
) -> str:
    """Создаёт папки для конкретного mailbox'a при его создании."""
    path = instance_voicemail_docker_dir(instance)

    # Создаём папки на docker пути
    for folder in VM_MAILBOX_FOLDERS:
        os.makedirs(os.path.join(path, context, mailbox, folder), exist_ok=True)

    uid, gid = config.ASTERISK_UID, config.ASTERISK_GID
    _chown_tree(os.path.join(path, context, mailbox), uid, gid)
    try:
        os.chmod(os.path.join(path, context, mailbox), 0o775)
    except OSError:
        pass

    # Создаём папки на API пути (если отличается)
    api_path = instance_voicemail_host_dir(instance)
    if api_path != path:
        for folder in VM_MAILBOX_FOLDERS:
            dest = os.path.join(api_path, context, mailbox, folder)
            os.makedirs(dest, exist_ok=True)
        _chown_tree(os.path.join(api_path, context, mailbox), uid, gid)

    return path


def ensure_instance_voicemail_dir(
    instance: AsteriskInstance,
    mailboxes: list[str] | None = None,
    *,
    context: str = VM_CONTEXT_NAME,
) -> str:
    """
    {config}/voicemail → /var/spool/asterisk/voicemail.
    Создаёт папки для указанных mailbox'ов и выставляет владельца asterisk (UID из .env).
    Если mailboxes=None, папки не создаются.
    """
    if mailboxes is None:
        # Ничего не создаём — папки создадутся при добавлении конкретных ящиков
        return instance_voicemail_docker_dir(instance)

    path = instance_voicemail_docker_dir(instance)
    os.makedirs(path, exist_ok=True)

    for box in mailboxes:
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
        for box in mailboxes:
            for folder in VM_MAILBOX_FOLDERS:
                dest = os.path.join(api_path, context, box, folder)
                os.makedirs(dest, exist_ok=True)
        _chown_tree(api_path, uid, gid)

    return path


def warn_if_empty_sounds_dir(instance: AsteriskInstance) -> str | None:
    """Пользовательские звуки — общая библиотека; vm-* — через astsoundsdir в образе."""
    _ = instance
    return None

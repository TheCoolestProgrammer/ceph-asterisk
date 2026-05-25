"""Тома Docker для контейнера Asterisk."""

import os

from utils.instance_voicemail_spool import VOICEMAIL_SUBDIR, ASTERISK_VM_CONTAINER_PATH


def build_asterisk_container_volumes(base_path: str) -> dict:
    """
    Собирает volumes для инстанса.

    Пустой каталог sounds не монтируется: иначе он перекрывает
    /var/lib/asterisk/sounds/en и пропадают все стандартные промпты.
    """
    volumes: dict = {
        base_path: {"bind": "/etc/asterisk", "mode": "rw"},
        f"{base_path}/drivers/odbc.ini": {"bind": "/etc/odbc.ini", "mode": "ro"},
        f"{base_path}/drivers/odbcinst.ini": {
            "bind": "/etc/odbcinst.ini",
            "mode": "ro",
        },
    }

    sounds_path = os.path.join(base_path, "sounds")
    if os.path.isdir(sounds_path) and any(os.scandir(sounds_path)):
        volumes[sounds_path] = {
            "bind": "/var/lib/asterisk/sounds/en",
            "mode": "ro",
        }

    voicemail_path = os.path.join(base_path, VOICEMAIL_SUBDIR)
    os.makedirs(voicemail_path, exist_ok=True)
    volumes[voicemail_path] = {
        "bind": ASTERISK_VM_CONTAINER_PATH,
        "mode": "rw",
    }

    return volumes


def compose_voicemail_volume(instance_config_path: str) -> str:
    """Проброс spool voicemail для docker-compose."""
    voicemail_path = os.path.join(instance_config_path, VOICEMAIL_SUBDIR)
    os.makedirs(voicemail_path, exist_ok=True)
    return f"{voicemail_path}:{ASTERISK_VM_CONTAINER_PATH}:rw"


def compose_sounds_volume(instance_config_path: str) -> str | None:
    """Путь для docker-compose volumes, если в инстансе есть звуковые файлы."""
    sounds_path = os.path.join(instance_config_path, "sounds")
    if os.path.isdir(sounds_path) and any(os.scandir(sounds_path)):
        return f"{sounds_path}:/var/lib/asterisk/sounds/en:ro"
    return None

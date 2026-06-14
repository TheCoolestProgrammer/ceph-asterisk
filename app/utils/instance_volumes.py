"""Тома Docker для контейнера Asterisk."""

import os

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import host_project_root
from app.utils.instance_voicemail_spool import VOICEMAIL_SUBDIR, ASTERISK_VM_CONTAINER_PATH


def shared_sounds_writable_dir() -> str:
    """Общая библиотека пользовательских звуков, доступная процессу API."""
    candidates = [
        os.path.join("/app", config.CONFIG_FOLDER, "sounds"),
        shared_sounds_docker_dir(),
    ]
    for path in candidates:
        parent = os.path.dirname(path)
        if os.path.isdir(parent):
            os.makedirs(path, exist_ok=True)
            return os.path.normpath(path)
    default = candidates[0]
    os.makedirs(default, exist_ok=True)
    return default


def shared_sounds_docker_dir() -> str:
    """Общая библиотека пользовательских звуков на хосте для bind-mount."""
    return os.path.join(host_project_root(), config.CONFIG_FOLDER, "sounds")


def sounds_dir_has_files(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    try:
        return any(os.scandir(path))
    except OSError:
        return False


def resolve_sounds_docker_mount_dir(instance: AsteriskInstance) -> str | None:
    """
    Host-путь общей библиотеки sounds для bind-mount.

    Пользовательские звуки хранятся только в asterisk_configs/sounds.
    Стандартные промпты Asterisk (vm-intro и др.) — в образе,
    astsoundsdir => /opt/asterisk-core-sounds в asterisk.conf.
    """
    _ = instance
    writable_path = shared_sounds_writable_dir()
    docker_path = shared_sounds_docker_dir()
    if sounds_dir_has_files(writable_path) or sounds_dir_has_files(docker_path):
        return docker_path
    return None


def instance_has_sounds_files(instance: AsteriskInstance) -> bool:
    """Есть ли файлы в общей библиотеке пользовательских звуков."""
    return resolve_sounds_docker_mount_dir(instance) is not None


def list_shared_sounds_dir_entries() -> list[os.DirEntry] | None:
    """Список файлов в общей библиотеке sounds."""
    for path in (shared_sounds_writable_dir(), shared_sounds_docker_dir()):
        if not os.path.isdir(path):
            continue
        try:
            entries = list(os.scandir(path))
        except OSError:
            continue
        if entries:
            return entries
    return None


def list_sounds_dir_entries(instance: AsteriskInstance) -> list[os.DirEntry] | None:
    """Совместимость: звуки всегда в общей библиотеке, не per-instance."""
    _ = instance
    return list_shared_sounds_dir_entries()


def build_asterisk_container_volumes(
    base_path: str,
    *,
    sounds_check_path: str | None = None,
) -> dict:
    """
    Собирает volumes для инстанса.

    Пустой каталог sounds не монтируется: иначе он перекрывает
    /var/lib/asterisk/sounds/en. Стандартные промпты — через astsoundsdir в образе.
    """
    volumes: dict = {
        base_path: {"bind": "/etc/asterisk", "mode": "rw"},
        f"{base_path}/drivers/odbc.ini": {"bind": "/etc/odbc.ini", "mode": "ro"},
        f"{base_path}/drivers/odbcinst.ini": {
            "bind": "/etc/odbcinst.ini",
            "mode": "ro",
        },
    }

    check_paths = [sounds_check_path] if sounds_check_path else []
    check_paths.extend([shared_sounds_docker_dir(), shared_sounds_writable_dir()])
    mount_source = next(
        (path for path in check_paths if path and sounds_dir_has_files(path)),
        None,
    )
    if mount_source:
        volumes[mount_source] = {
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


def compose_sounds_volume(instance: AsteriskInstance) -> str | None:
    """Общая библиотека sounds для docker-compose, если в ней есть файлы."""
    mount_dir = resolve_sounds_docker_mount_dir(instance)
    if mount_dir is None:
        return None
    return f"{mount_dir}:/var/lib/asterisk/sounds/en:ro"

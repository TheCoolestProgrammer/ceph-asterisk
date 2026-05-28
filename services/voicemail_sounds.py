"""Проверка наличия звуковых промптов app_voicemail (vm-intro и др.)."""

import os

from services.asterisk_reload import AsteriskReloadError, run_asterisk_cli
from utils.instance_paths import docker_volume_config_dir
from models.asterisk_instance import AsteriskInstance


def warn_if_sounds_mount_overrides_defaults(instance: AsteriskInstance) -> str | None:
    """
    Пустой или неполный каталог {config}/sounds монтируется поверх
    /var/lib/asterisk/sounds/en и убирает стандартные vm-*.
    """
    sounds_path = os.path.join(docker_volume_config_dir(instance), "sounds")
    if not os.path.isdir(sounds_path):
        return None
    try:
        entries = list(os.scandir(sounds_path))
    except OSError:
        return None
    if not entries:
        return (
            "Каталог sounds/ у инстанса пуст: удалите его или добавьте vm-intro.* "
            "(иначе после пересборки образа промпты снова пропадут при монтировании)."
        )
    has_vm = any(
        e.name.startswith("vm-intro") for e in entries if e.is_file()
    )
    if not has_vm:
        return (
            "В sounds/ инстанса нет vm-intro — каталог монтируется поверх "
            "стандартных промптов. Удалите sounds/ или скопируйте туда файлы из "
            "asterisk-core-sounds-en."
        )
    return None


def check_voicemail_prompts(instance_name: str) -> str | None:
    """
    Проверяет базовые voicemail промпты в контейнере через CLI.
    Возвращает текст предупреждения или None, если промпты найдены.
    """
    required_prompts = ("vm-intro", "vm-password")
    missing: list[str] = []
    for prompt in required_prompts:
        try:
            result = run_asterisk_cli(
                instance_name, f"core show file {prompt}", strict=False
            )
        except AsteriskReloadError as e:
            return f"Не удалось проверить звуки voicemail: {e.message}"
        combined = f"{result.stdout}\n{result.stderr}".lower()
        if "does not exist" in combined or "no such file" in combined:
            missing.append(prompt)

    if missing:
        missing_list = ", ".join(missing)
        return (
            f"В контейнере не найдены voicemail-подсказки ({missing_list}) — "
            "VoiceMail/VoiceMailMain может завершаться сразу. "
            "Пересоберите образ (docker/asterisk.Dockerfile), в asterisk.conf "
            "должно быть astsoundsdir => /opt/asterisk-core-sounds, затем reload."
        )
    return None

"""Проверка наличия звуковых промптов app_voicemail (vm-intro и др.)."""

from app.services.asterisk_reload import AsteriskReloadError, run_asterisk_cli
from app.models.asterisk_instance import AsteriskInstance


def warn_if_sounds_mount_overrides_defaults(instance: AsteriskInstance) -> str | None:
    """
    Пользовательские звуки — общая библиотека asterisk_configs/sounds.
    Стандартные промпты voicemail — astsoundsdir => /opt/asterisk-core-sounds.
    """
    _ = instance
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

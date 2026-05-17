"""Сборка образа Asterisk (docker/asterisk.Dockerfile)."""

import logging
import os
import subprocess

import docker
from docker.errors import ImageNotFound

from config import config

logger = logging.getLogger(__name__)

ASTERISK_DOCKER_DIR = "docker"
ASTERISK_DOCKERFILE = "asterisk.Dockerfile"

_VM_INTRO_CHECK = (
    "test -f /var/lib/asterisk/sounds/en/vm-intro.ulaw "
    "|| test -f /var/lib/asterisk/sounds/en/vm-intro.gsm "
    "|| test -f /usr/share/asterisk/sounds/en/vm-intro.ulaw"
)


def asterisk_image_build_context() -> str:
    return os.path.join(config.PROJECT_PATH.rstrip("/"), ASTERISK_DOCKER_DIR)


def build_asterisk_image(client, *, tag: str | None = None):
    tag = tag or config.ASTERISK_IMAGE_TAG
    logger.info("Building Asterisk image %s from %s", tag, asterisk_image_build_context())
    return client.images.build(
        path=asterisk_image_build_context(),
        dockerfile=ASTERISK_DOCKERFILE,
        tag=tag,
        rm=True,
        pull=True,
    )


def image_has_voicemail_sounds(tag: str | None = None) -> bool:
    """Проверяет наличие vm-intro в образе (не в запущенном контейнере)."""
    tag = tag or config.ASTERISK_IMAGE_TAG
    try:
        subprocess.run(
            ["docker", "image", "inspect", tag],
            capture_output=True,
            check=True,
            timeout=15,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False

    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", tag, "-c", _VM_INTRO_CHECK],
        capture_output=True,
        timeout=60,
    )
    return result.returncode == 0


def ensure_asterisk_image(client=None, *, force_rebuild: bool = False):
    """
    Возвращает образ Asterisk с промптами voicemail.
    Пересобирает, если образа нет, force_rebuild или нет vm-intro.
    """
    client = client or docker.from_env()
    tag = config.ASTERISK_IMAGE_TAG

    if not force_rebuild:
        try:
            image = client.images.get(tag)
            if image_has_voicemail_sounds(tag):
                return image
            logger.warning(
                "Image %s exists but vm-intro missing; rebuilding", tag
            )
        except ImageNotFound:
            pass

    image, _build_logs = build_asterisk_image(client, tag=tag)
    if not image_has_voicemail_sounds(tag):
        raise RuntimeError(
            f"Image {tag} built but vm-intro still missing; "
            "check docker/asterisk.Dockerfile build logs"
        )
    return image

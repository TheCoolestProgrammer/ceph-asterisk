"""Сборка образа Asterisk (deploy/docker/asterisk.Dockerfile)."""

import logging
import os
import subprocess

import docker
from docker.errors import ImageNotFound

from app.core.config import config
from app.utils.instance_paths import host_project_root

logger = logging.getLogger(__name__)

ASTERISK_DOCKER_DIR = "deploy/docker"
ASTERISK_DOCKERFILE = "asterisk.Dockerfile"

# Промпты в /opt — не перекрываются VOLUME базового образа на /var/lib/asterisk/sounds
_VM_SOUNDS_CHECK = (
    "ls -la /opt/asterisk-core-sounds/en/vm-intro.ulaw "
    "/opt/asterisk-core-sounds/en/vm-password.ulaw "
    "&& test -f /opt/asterisk-core-sounds/en/vm-intro.ulaw "
    "&& test -f /opt/asterisk-core-sounds/en/vm-password.ulaw"
)


def asterisk_image_build_context() -> str:
    """
    Каталог для docker build (должен существовать в процессе API).

    docker-py упаковывает context в tar из локальной ФС клиента.
    В контейнере FastAPI это /app/deploy/docker, на хосте — PROJECT_PATH/deploy/docker.
    """
    candidates = [
        os.path.join("/app", ASTERISK_DOCKER_DIR),
        os.path.join(config.PROJECT_PATH.rstrip("/"), ASTERISK_DOCKER_DIR),
        os.path.join(host_project_root(), ASTERISK_DOCKER_DIR),
    ]
    seen: set[str] = set()
    for ctx in candidates:
        ctx = os.path.normpath(ctx)
        if ctx in seen:
            continue
        seen.add(ctx)
        dockerfile = os.path.join(ctx, ASTERISK_DOCKERFILE)
        if os.path.isdir(ctx) and os.path.isfile(dockerfile):
            return ctx
    raise FileNotFoundError(
        "Не найден deploy/docker/asterisk.Dockerfile. "
        "Проверьте монтирование /app в API-контейнер или PROJECT_PATH."
    )


def build_asterisk_image(client, *, tag: str | None = None, nocache: bool = False):
    tag = tag or config.ASTERISK_IMAGE_TAG
    ctx = asterisk_image_build_context()
    logger.info("Building Asterisk image %s from %s (nocache=%s)", tag, ctx, nocache)
    return client.images.build(
        path=ctx,
        dockerfile=ASTERISK_DOCKERFILE,
        tag=tag,
        rm=True,
        pull=True,
        nocache=nocache,
    )


def image_has_voicemail_sounds(tag: str | None = None) -> bool:
    """Проверяет vm-intro и vm-password в образе (путь /opt/...)."""
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
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--entrypoint",
            "sh",
            tag,
            "-c",
            _VM_SOUNDS_CHECK,
        ],
        capture_output=True,
        timeout=120,
    )
    return result.returncode == 0


def ensure_asterisk_image(client=None, *, force_rebuild: bool = False):
    """
    Возвращает образ Asterisk с промптами voicemail.
    Пересобирает, если образа нет, force_rebuild или не хватает vm-*.
    """
    client = client or docker.from_env()
    tag = config.ASTERISK_IMAGE_TAG

    if not force_rebuild:
        try:
            image = client.images.get(tag)
            if image_has_voicemail_sounds(tag):
                return image
            logger.warning(
                "Image %s exists but required vm-* prompts missing; rebuilding", tag
            )
        except ImageNotFound:
            pass

    image, _build_logs = build_asterisk_image(
        client, tag=tag, nocache=force_rebuild
    )
    if not image_has_voicemail_sounds(tag):
        logger.warning(
            "Image %s: required vm-* prompts not found in docker run check; "
            "ensure astsoundsdir => /opt/asterisk-core-sounds in asterisk.conf",
            tag,
        )
    return image

import logging
import os
import subprocess

import yaml

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.services.asterisk_reload import container_name_for_instance
from app.services.filebeat_config import write_filebeat_config
from app.utils.asterisk_image import ensure_asterisk_image
from app.utils.instance_paths import docker_volume_config_dir, host_project_root
from app.utils.instance_volumes import compose_sounds_volume, compose_voicemail_volume

logger = logging.getLogger(__name__)


class InstanceComposeError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        self.message = message
        self.stderr = stderr
        super().__init__(message)


def compose_project_name(instance_name: str) -> str:
    """Уникальный compose-проект на инстанс (иначе сервис filebeat конфликтует)."""
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in instance_name)
    return f"asterisk-{safe}"


def compose_workdir() -> str:
    api_path = f"/app/{config.COMPOSE_FOLDER}"
    if os.path.isdir("/app"):
        return api_path
    return os.path.join(host_project_root(), config.COMPOSE_FOLDER)


def compose_filename(instance_name: str) -> str:
    return f"docker-compose-{instance_name}.yml"


def compose_cli(instance_name: str, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        compose_project_name(instance_name),
        "-f",
        compose_filename(instance_name),
        *args,
    ]


def filebeat_config_host_path(instance_name: str) -> str:
    return os.path.join(
        host_project_root(),
        config.COMPOSE_FOLDER,
        f"filebeat-{instance_name}.yml",
    )


def build_compose_config(instance: AsteriskInstance) -> dict:
    instance_config_path = docker_volume_config_dir(instance)
    docker_dir = os.path.join(host_project_root(), "deploy", "docker")
    volumes = [
        f"{instance_config_path}:/etc/asterisk:rw",
        f"{instance_config_path}/drivers/odbc.ini:/etc/odbc.ini",
        f"{instance_config_path}/drivers/odbcinst.ini:/etc/odbcinst.ini",
        f"{instance_config_path}/asterisk_logs:/var/log/asterisk",
    ]
    sounds_volume = compose_sounds_volume(instance)
    if sounds_volume:
        volumes.insert(1, sounds_volume)
    volumes.insert(1, compose_voicemail_volume(instance_config_path))

    filebeat_service = f"filebeat-{instance.name}"

    return {
        "services": {
            instance.name: {
                "image": config.ASTERISK_IMAGE_TAG,
                "build": {
                    "context": docker_dir,
                    "dockerfile": "asterisk.Dockerfile",
                },
                "container_name": container_name_for_instance(instance.name),
                "ports": [
                    f"{instance.sip_port}:{instance.sip_port}/udp",
                    f"{instance.sip_port}:{instance.sip_port}/tcp",
                    f"{instance.http_port}:{instance.http_port}/tcp",
                    f"{instance.rtp_port_start}-{instance.rtp_port_end}:{instance.rtp_port_start}-{instance.rtp_port_end}/udp",
                    f"{instance.ami_port}:{instance.ami_port}",
                ],
                "volumes": volumes,
                "networks": ["ceph-asterisk_default"],
                "privileged": True,
            },
            filebeat_service: {
                "image": "docker.elastic.co/beats/filebeat:8.12.0",
                "container_name": f"filebeat-{instance.name}",
                "user": "root",
                "environment": {"PBX_NAME": instance.name},
                "networks": ["ceph-asterisk_default"],
                "volumes": [
                    f"{filebeat_config_host_path(instance.name)}:/usr/share/filebeat/filebeat.yml:ro",
                    f"{instance_config_path}/asterisk_logs:/var/log/asterisk:ro",
                ],
                "depends_on": [instance.name],
            },
        },
        "networks": {"ceph-asterisk_default": {"external": True}},
    }


def _container_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _missing_stack_containers(instance_name: str) -> list[str]:
    expected = (
        container_name_for_instance(instance_name),
        f"filebeat-{instance_name}",
    )
    return [name for name in expected if not _container_running(name)]


def stop_instance_stack(instance: AsteriskInstance, *, timeout: int = 60) -> None:
    """Останавливает asterisk и filebeat инстанса."""
    from app.services.instance_container import (
        remove_asterisk_container,
        remove_filebeat_container,
    )

    compose_path = compose_workdir()
    filename = compose_filename(instance.name)
    compose_file = os.path.join(compose_path, filename)
    if os.path.isfile(compose_file):
        subprocess.run(
            compose_cli(instance.name, "down"),
            cwd=compose_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return
    remove_asterisk_container(instance.name)
    remove_filebeat_container(instance.name)


def sync_instance_compose(
    instance: AsteriskInstance,
    *,
    timeout: int = 180,
    force_rebuild_image: bool = False,
) -> None:
    """Перезаписывает docker-compose и поднимает asterisk + filebeat."""
    compose_path = compose_workdir()
    filename = compose_filename(instance.name)
    filebeat_service = f"filebeat-{instance.name}"

    os.makedirs(compose_path, exist_ok=True)
    write_filebeat_config(instance.name)
    ensure_asterisk_image(force_rebuild=force_rebuild_image)

    with open(os.path.join(compose_path, filename), "w", encoding="utf-8") as f:
        yaml.dump(build_compose_config(instance), f)

    cmd = compose_cli(instance.name, "up", "-d", "--no-build")
    result = subprocess.run(
        cmd,
        cwd=compose_path,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.warning(
            "compose up --no-build failed for %s, retrying with build: %s",
            instance.name,
            (result.stderr or result.stdout or "").strip(),
        )
        result = subprocess.run(
            compose_cli(instance.name, "up", "-d"),
            cwd=compose_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    if result.returncode != 0:
        raise InstanceComposeError(
            f"Failed to apply compose for {instance.name}",
            stderr=(result.stderr or result.stdout or "").strip(),
        )

    missing = _missing_stack_containers(instance.name)
    if missing:
        logger.warning(
            "Stack incomplete after compose up (%s), starting filebeat: %s",
            instance.name,
            ", ".join(missing),
        )
        fb = subprocess.run(
            compose_cli(instance.name, "up", "-d", filebeat_service),
            cwd=compose_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if fb.returncode != 0:
            raise InstanceComposeError(
                f"Filebeat failed to start for {instance.name}",
                stderr=(fb.stderr or fb.stdout or "").strip(),
            )
        missing = _missing_stack_containers(instance.name)

    if missing:
        raise InstanceComposeError(
            f"Containers not running for {instance.name}: {', '.join(missing)}",
            stderr=(result.stderr or result.stdout or "").strip(),
        )

"""Запуск и пересоздание контейнера Asterisk с корректным volume конфигов."""

import json
import logging
import os
import subprocess

import docker

from config import config
from models.asterisk_instance import AsteriskInstance
from services.asterisk_reload import container_name_for_instance
from utils.instance_paths import docker_volume_config_dir
from utils.asterisk_image import ensure_asterisk_image
from utils.instance_volumes import build_asterisk_container_volumes

logger = logging.getLogger(__name__)


def get_mount_source(container_name: str, destination: str = "/etc/asterisk") -> str | None:
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name, "--format", "{{json .Mounts}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        mounts = json.loads(result.stdout or "[]")
        for mount in mounts:
            if mount.get("Destination") == destination:
                return mount.get("Source")
    except (json.JSONDecodeError, subprocess.SubprocessError, OSError) as e:
        logger.debug("get_mount_source failed: %s", e)
    return None


def file_exists_in_container(container_name: str, path: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "test", "-f", path],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def get_container_published_ports(container_name: str) -> dict[str, str | None]:
    """Проброс портов контейнера на хост (docker inspect Ports)."""
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name, "--format", "{{json .NetworkSettings.Ports}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {}
        raw = json.loads(result.stdout or "{}")
        out: dict[str, str | None] = {}
        for container_port, bindings in raw.items():
            if bindings and isinstance(bindings, list):
                out[container_port] = bindings[0].get("HostPort")
            else:
                out[container_port] = None
        return out
    except (json.JSONDecodeError, subprocess.SubprocessError, OSError) as e:
        logger.debug("get_container_published_ports failed: %s", e)
        return {}


def verify_instance_network(instance: AsteriskInstance) -> dict:
    """Проверка, что SIP-порт опубликован на хост (иначе REGISTER не дойдёт)."""
    container = container_name_for_instance(instance.name)
    ports = get_container_published_ports(container)
    sip_udp = ports.get(f"{instance.sip_port}/udp")
    sip_tcp = ports.get(f"{instance.sip_port}/tcp")
    sip_published = bool(sip_udp or sip_tcp)
    rtp_published = 0
    for port in range(instance.rtp_port_start, instance.rtp_port_end + 1):
        if ports.get(f"{port}/udp"):
            rtp_published += 1
    rtp_total = instance.rtp_port_end - instance.rtp_port_start + 1
    rtp_ok = rtp_published == rtp_total
    return {
        "container": container,
        "expected_sip_port": instance.sip_port,
        "rtp_range": f"{instance.rtp_port_start}-{instance.rtp_port_end}",
        "rtp_ports_published": rtp_published,
        "rtp_ports_total": rtp_total,
        "rtp_reachable": rtp_ok,
        "published_ports": ports,
        "sip_udp_on_host": sip_udp,
        "sip_tcp_on_host": sip_tcp,
        "sip_reachable_from_lan": sip_published,
        "fix": (
            None
            if sip_published and rtp_ok
            else "POST /instances/{id}/recreate-container — пробросить SIP и RTP UDP на хост"
        ),
    }


def verify_instance_config_mount(instance: AsteriskInstance) -> dict:
    """Сравнивает ожидаемый каталог на хосте с фактическим bind-mount в контейнере."""
    expected = docker_volume_config_dir(instance)
    container = container_name_for_instance(instance.name)
    actual = get_mount_source(container)
    pjsip_users_name = "pjsip_users.conf"
    host_pjsip = os.path.join(expected, pjsip_users_name)

    return {
        "container": container,
        "expected_host_dir": expected,
        "actual_mount_source": actual,
        "mount_matches_expected": actual == expected if actual else False,
        "pjsip_users_on_host": os.path.isfile(host_pjsip),
        "pjsip_users_in_container": file_exists_in_container(
            container, f"/etc/asterisk/{pjsip_users_name}"
        ),
        "fix": (
            "POST /instances/{id}/recreate-container — пересоздать контейнер "
            f"с volume {expected}:/etc/asterisk"
            if actual != expected
            else None
        ),
    }


def remove_asterisk_container(instance_name: str) -> None:
    client = docker.from_env()
    name = container_name_for_instance(instance_name)
    try:
        container = client.containers.get(name)
        container.stop(timeout=15)
        container.remove()
    except docker.errors.NotFound:
        pass


def run_asterisk_container(
    instance: AsteriskInstance,
    db,
    *,
    force_rebuild_image: bool = False,
) -> None:
    """Создаёт контейнер asterisk-{name} с volume конфигов с хоста."""
    client = docker.from_env()
    image = ensure_asterisk_image(client, force_rebuild=force_rebuild_image)

    base_path = docker_volume_config_dir(instance)
    port_bindings = {
        f"{instance.sip_port}/udp": instance.sip_port,
        f"{instance.sip_port}/tcp": instance.sip_port,
        f"{instance.http_port}/tcp": instance.http_port,
    }
    for port in range(instance.rtp_port_start, instance.rtp_port_end + 1):
        port_bindings[f"{port}/udp"] = port

    client.containers.run(
        image=image,
        name=container_name_for_instance(instance.name),
        detach=True,
        privileged=True,
        ports=port_bindings,
        network="ceph-asterisk_default",
        volumes=build_asterisk_container_volumes(base_path),
    )
    instance.status = "running"
    db.commit()
    logger.info("Container asterisk-%s started, config volume %s", instance.name, base_path)


def recreate_asterisk_container(
    instance: AsteriskInstance,
    db,
    *,
    force_rebuild_image: bool = False,
) -> str:
    """Останавливает и пересоздаёт контейнер с актуальным bind-mount конфигов."""
    expected = docker_volume_config_dir(instance)
    remove_asterisk_container(instance.name)
    run_asterisk_container(instance, db, force_rebuild_image=force_rebuild_image)
    return expected

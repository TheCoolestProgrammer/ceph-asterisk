import subprocess

import yaml

from config import config
from models.asterisk_instance import AsteriskInstance
from utils.instance_paths import docker_volume_config_dir
from utils.instance_volumes import compose_sounds_volume


class InstanceComposeError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        self.message = message
        self.stderr = stderr
        super().__init__(message)


def build_compose_config(instance: AsteriskInstance) -> dict:
    instance_config_path = docker_volume_config_dir(instance)
    volumes = [
        f"{instance_config_path}:/etc/asterisk:rw",
        f"{instance_config_path}/drivers/odbc.ini:/etc/odbc.ini",
        f"{instance_config_path}/drivers/odbcinst.ini:/etc/odbcinst.ini",
        f"{instance_config_path}/asterisk_logs:/var/log/asterisk",
    ]
    sounds_volume = compose_sounds_volume(instance_config_path)
    if sounds_volume:
        volumes.insert(1, sounds_volume)

    return {
        "version": "3.8",
        "services": {
            instance.name: {
                "build": {
                    "context": f"/app/docker",
                    "dockerfile": "asterisk.Dockerfile",
                },
                "container_name": f"asterisk-{instance.name}",
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
            "filebeat": {
                "image": "docker.elastic.co/beats/filebeat:8.12.0",
                "container_name": f"filebeat-{instance.name}",
                "user": "root",
                "environment": {"PBX_NAME": instance.name},
                "networks": ["ceph-asterisk_default"],
                "volumes": [
                    f"{config.PROJECT_PATH.rstrip('/')}/{config.COMPOSE_FOLDER}/filebeat-{instance.name}.yml:/usr/share/filebeat/filebeat.yml:ro",
                    f"{instance_config_path}/asterisk_logs:/var/log/asterisk:ro",
                ],
                "depends_on": [instance.name],
            },
        },
        "networks": {"ceph-asterisk_default": {"external": True}},
    }


def sync_instance_compose(instance: AsteriskInstance, *, timeout: int = 120) -> None:
    """Перезаписывает docker-compose и применяет новые пробросы портов (в т.ч. AMI)."""
    compose_path = f"/app/{config.COMPOSE_FOLDER}/"
    filename = f"docker-compose-{instance.name}.yml"

    with open(f"{compose_path}/{filename}", "w", encoding="utf-8") as f:
        yaml.dump(build_compose_config(instance), f)

    result = subprocess.run(
        ["docker", "compose", "-f", filename, "up", "-d"],
        cwd=compose_path,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        if any(
            marker in combined
            for marker in ("started", "recreated", "running", "created")
        ):
            return
        raise InstanceComposeError(
            f"Failed to apply compose for {instance.name}",
            stderr=result.stderr.strip(),
        )

import subprocess

import yaml

from config import config
from models.asterisk_instance import AsteriskInstance


class InstanceComposeError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        self.message = message
        self.stderr = stderr
        super().__init__(message)


def build_compose_config(instance: AsteriskInstance) -> dict:
    return {
        "version": "3.8",
        "services": {
            instance.name: {
                "build": {
                    "context": f"/app/{config.COMPOSE_FOLDER}",
                    "dockerfile": "dockerfile",
                },
                "container_name": f"asterisk-{instance.name}",
                "ports": [
                    f"{instance.sip_port}:{instance.sip_port}/udp",
                    f"{instance.sip_port}:{instance.sip_port}/tcp",
                    f"{instance.http_port}:{instance.http_port}/tcp",
                    f"{instance.rtp_port_start}-{instance.rtp_port_end}:{instance.rtp_port_start}-{instance.rtp_port_end}/udp",
                    f"{instance.ami_port}:{instance.ami_port}",
                ],
                "volumes": [
                    f"{config.PROJECT_PATH}/{config.CONFIG_FOLDER}/{instance.name}:/etc/asterisk:rw",
                    f"{config.PROJECT_PATH}/{config.CONFIG_FOLDER}/sounds:/var/lib/asterisk/sounds/en:ro",
                    f"{config.PROJECT_PATH}/{config.CONFIG_FOLDER}/{instance.name}/drivers/odbc.ini:/etc/odbc.ini",
                    f"{config.PROJECT_PATH}/{config.CONFIG_FOLDER}/{instance.name}/drivers/odbcinst.ini:/etc/odbcinst.ini",
                    f"{config.PROJECT_PATH}/{config.CONFIG_FOLDER}/{instance.name}/asterisk_logs:/var/log/asterisk",
                ],
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
                    f"/{config.PROJECT_PATH}/{config.COMPOSE_FOLDER}/filebeat-{instance.name}.yml:/usr/share/filebeat/filebeat.yml:ro",
                    f"{config.PROJECT_PATH}/{config.CONFIG_FOLDER}/{instance.name}/asterisk_logs:/var/log/asterisk:ro",
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

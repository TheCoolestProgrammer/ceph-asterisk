import os

import yaml

from app.core.config import config


def write_filebeat_config(instance_name: str) -> str:
    """Пишет filebeat-{name}.yml в каталог compose инстанса. Возвращает путь к файлу."""
    compose_path = f"/app/{config.COMPOSE_FOLDER}"
    os.makedirs(compose_path, exist_ok=True)

    filebeat_config = {
        "filebeat.inputs": [
            {
                "type": "log",
                "enabled": True,
                "paths": ["/var/log/asterisk/messages*"],
                "fields": {"pbx_id": "${PBX_NAME}"},
                "fields_under_root": True,
            }
        ],
        "processors": [
            {
                "dissect": {
                    "tokenizer": "[%{timestamp}] %{level}[%{pid}] %{file}: %{message}",
                    "field": "message",
                    "target_prefix": "asterisk",
                    "ignore_failure": True,
                }
            },
            {
                "timestamp": {
                    "field": "asterisk.timestamp",
                    "layouts": ["2006-01-02 15:04:05"],
                }
            },
        ],
        "output.elasticsearch": {
            "hosts": ["elasticsearch:9200"],
            "index": "raw-asterisk-logs",
        },
        "setup.ilm.enabled": False,
        "setup.data_stream.enabled": False,
        "setup.template.name": "asterisk",
        "setup.template.pattern": "asterisk-*",
    }
    filename = f"filebeat-{instance_name}.yml"
    path = f"{compose_path}/{filename}"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(filebeat_config, f)
    return path

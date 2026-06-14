"""Модули Asterisk для app_voicemail (запись и прослушивание через *97)."""

import os

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import writable_config_dir

VOICEMAIL_MODULE_LINES = (
    "load => app_voicemail.so",
)


def ensure_voicemail_modules(instance: AsteriskInstance) -> None:
    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return
    modules_path = os.path.join(config_dir, "modules.conf")
    if not os.path.isfile(modules_path):
        return
    with open(modules_path, encoding="utf-8") as f:
        content = f.read()
    if all(line in content for line in VOICEMAIL_MODULE_LINES):
        return
    lines = content.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().startswith("load => app_dial"):
            out.extend(VOICEMAIL_MODULE_LINES)
            inserted = True
    if not inserted:
        out.extend(VOICEMAIL_MODULE_LINES)
    with open(modules_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    os.chmod(modules_path, 0o777)
    try:
        os.chown(modules_path, config.ASTERISK_UID, config.ASTERISK_GID)
    except OSError:
        pass

"""MOH, форматы аудио и modules.conf для голоса в звонках/очереди."""

import os

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import writable_config_dir

MEDIA_MODULE_LINES = (
    "load => res_musiconhold.so",
    "load => format_wav.so",
    "load => format_gsm.so",
    "load => format_pcm.so",
    "load => bridge_simple.so",
    "load => bridge_softmix.so",
)

MUSICONHOLD_CONF = """[general]
[default]
mode=files
directory=/var/lib/asterisk/moh
random=yes
"""


def ensure_media_modules(instance: AsteriskInstance) -> None:
    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return
    modules_path = os.path.join(config_dir, "modules.conf")
    if not os.path.isfile(modules_path):
        return
    with open(modules_path, encoding="utf-8") as f:
        content = f.read()
    if all(line in content for line in MEDIA_MODULE_LINES):
        return
    lines = content.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().startswith("load => app_playback"):
            out.extend(MEDIA_MODULE_LINES)
            inserted = True
    if not inserted:
        out.extend(MEDIA_MODULE_LINES)
    with open(modules_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    os.chmod(modules_path, 0o777)


def write_musiconhold_conf(instance: AsteriskInstance) -> None:
    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return
    path = os.path.join(config_dir, "musiconhold.conf")
    with open(path, "w", encoding="utf-8") as f:
        f.write(MUSICONHOLD_CONF)
    os.chmod(path, 0o777)
    try:
        os.chown(path, config.ASTERISK_UID, config.ASTERISK_GID)
    except OSError:
        pass

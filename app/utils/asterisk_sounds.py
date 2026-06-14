"""astsoundsdir на диске инстанса (asterisk.conf не в ODBC)."""

import os
import re

from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import writable_config_dir

ASTSOUNDSDIR_LINE = "astsoundsdir => /opt/asterisk-core-sounds\n"
ASTSOUNDSDIR_VALUE = "/opt/asterisk-core-sounds"


def ensure_astsoundsdir_on_disk(instance: AsteriskInstance) -> bool:
    """Добавляет astsoundsdir в asterisk.conf инстанса, если ещё нет."""
    path = os.path.join(writable_config_dir(instance), "asterisk.conf")
    if not os.path.isfile(path):
        return False

    with open(path, encoding="utf-8") as f:
        content = f.read()

    if re.search(r"^\s*astsoundsdir\s*=>", content, re.MULTILINE | re.IGNORECASE):
        if ASTSOUNDSDIR_VALUE in content:
            return False
        content = re.sub(
            r"^\s*astsoundsdir\s*=>.*$",
            f"astsoundsdir => {ASTSOUNDSDIR_VALUE}",
            content,
            count=1,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        changed = True
    else:
        if "[directories]" in content:
            content = content.replace(
                "[directories]\n",
                f"[directories]\n{ASTSOUNDSDIR_LINE}",
                1,
            )
        else:
            content = f"[directories]\n{ASTSOUNDSDIR_LINE}\n" + content
        changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return changed

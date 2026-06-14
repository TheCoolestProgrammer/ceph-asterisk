"""Генерация pjsip_users.conf из БД (источник истины — ps_*)."""

import os
from enum import Enum

from sqlalchemy.orm import Session, joinedload

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import writable_config_dir
from app.models.sip_user import PjsipEndpoint, PjsipAor

PJSIP_USERS_FILENAME = "pjsip_users.conf"

SORCERY_CONF_CONTENT = """[res_pjsip]
; transport/global — с диска; endpoint/auth/aor — ODBC VIEW (AOR id = номер, без дубля [101] в ini)
transport=config,pjsip.conf,criteria=type=transport
global=config,pjsip.conf,criteria=type=global
endpoint=realtime,ps_endpoints
auth=realtime,ps_auths
aor=realtime,ps_aors
; contacts в RAM (ODBC ps_contacts часто ломает REGISTER — неполная схема INSERT)
contact=memory

[res_pjsip_endpoint_identifier_ip]
identify=realtime,ps_endpoint_id_ips

[res_pjsip_endpoint_identifier_user]
endpoint=realtime,ps_endpoints
"""

MODULES_SORCERY_PRELOAD = (
    "preload => res_sorcery.so",
    "preload => res_sorcery_config.so",
    "preload => res_sorcery_realtime.so",
    "preload => res_sorcery_memory.so",
)


def _format_callerid(callerid: str | None, extension: str) -> str:
    """Формат PJSIP: "Имя" <ext>. Значения из БД вида 'string / <101>' ломают парсер."""
    if not callerid or not str(callerid).strip():
        return f'"{extension}" <{extension}>'
    raw = str(callerid).strip()
    if "<" in raw and ">" in raw:
        name = raw.split("<", 1)[0].strip().strip('"').strip("/").strip()
        if not name:
            name = extension
        return f'"{name}" <{extension}>'
    return f'"{raw}" <{extension}>'


def _yesno(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _lines_for_section(name: str, options: dict[str, object]) -> list[str]:
    rows = [f"[{name}]", f"type={options['type']}"]
    for key, val in options.items():
        if key == "type":
            continue
        text = _yesno(val) if isinstance(val, Enum) else val
        if text is None or text == "":
            continue
        rows.append(f"{key}={text}")
    return rows


def render_pjsip_users_conf(cdr_db: Session, reg_server: str) -> str:
    """Собирает pjsip_users.conf для одного инстанса из ps_*."""
    endpoints = (
        cdr_db.query(PjsipEndpoint)
        .options(
            joinedload(PjsipEndpoint.aors_fk),
            joinedload(PjsipEndpoint.auths_fk),
        )
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)
        .filter(PjsipAor.reg_server == reg_server)
        .all()
    )

    lines = [
        f"; generated from DB for {reg_server}",
        "; auto-updated on reload / user CRUD",
        "",
    ]

    for ep in endpoints:
        aor = ep.aors_fk
        auth = ep.auths_fk
        if not aor or not auth:
            continue

        lines.extend(
            _lines_for_section(
                aor.id,
                {
                    "type": "aor",
                    "max_contacts": aor.max_contacts,
                    "default_expiration": aor.default_expiration,
                    "minimum_expiration": aor.minimum_expiration,
                    "qualify_frequency": aor.qualify_frequency,
                    "remove_existing": aor.remove_existing,
                },
            )
        )
        lines.append("")

        lines.extend(
            _lines_for_section(
                auth.id,
                {
                    "type": "auth",
                    "auth_type": auth.auth_type,
                    "username": auth.username,
                    "password": auth.password,
                },
            )
        )
        lines.append("")

        lines.extend(
            _lines_for_section(
                ep.id,
                {
                    "type": "endpoint",
                    "transport": ep.transport,
                    "context": ep.context,
                    "aors": ep.aors,
                    "auth": ep.auth,
                    "callerid": _format_callerid(ep.callerid, ep.id),
                    "disallow": ep.disallow,
                    "allow": ep.allow,
                    "direct_media": ep.direct_media,
                    "rewrite_contact": ep.rewrite_contact,
                    "rtp_symmetric": ep.rtp_symmetric,
                    "force_rport": ep.force_rport,
                    "trust_id_inbound": ep.trust_id_inbound,
                    "trust_id_outbound": ep.trust_id_outbound,
                },
            )
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def ensure_pjsip_modules_preload(instance: AsteriskInstance) -> None:
    """Добавляет preload sorcery в modules.conf (нужен для config/realtime wizard)."""
    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return
    filepath = os.path.join(config_dir, "modules.conf")
    if not os.path.isfile(filepath):
        return
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    if all(line in content for line in MODULES_SORCERY_PRELOAD):
        return
    lines = content.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().lower() == "autoload = yes":
            out.extend(MODULES_SORCERY_PRELOAD)
            inserted = True
    if not inserted:
        out = ["[modules]", "autoload = yes", *MODULES_SORCERY_PRELOAD, *lines]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    os.chmod(filepath, 0o777)


def write_pjsip_sorcery_conf(instance: AsteriskInstance) -> str:
    """Обновляет sorcery.conf: transport в pjsip.conf, endpoint/auth/aor в pjsip_users.conf."""
    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return ""
    os.makedirs(config_dir, exist_ok=True)
    filepath = os.path.join(config_dir, "sorcery.conf")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(SORCERY_CONF_CONTENT)
    os.chmod(filepath, 0o777)
    try:
        os.chown(filepath, config.ASTERISK_UID, config.ASTERISK_GID)
    except OSError:
        pass
    ensure_pjsip_modules_preload(instance)
    return filepath


def write_pjsip_users_conf(instance: AsteriskInstance, cdr_db: Session) -> str:
    """Пишет pjsip_users.conf на диск. Возвращает путь к файлу."""
    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return ""
    os.makedirs(config_dir, exist_ok=True)

    content = render_pjsip_users_conf(cdr_db, instance.name)
    filepath = os.path.join(config_dir, PJSIP_USERS_FILENAME)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(filepath, 0o777)
    try:
        os.chown(filepath, config.ASTERISK_UID, config.ASTERISK_GID)
    except OSError:
        pass
    return filepath

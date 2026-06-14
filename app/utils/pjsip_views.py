"""VIEW в MySQL для изоляции PJSIP realtime по АТС (reg_server = имя инстанса)."""

import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import config
from app.models.asterisk_instance import AsteriskInstance
from app.utils.instance_paths import writable_config_dir

PJSIP_VIEW_SUFFIX = "_inst_"

# Только колонки, которые понимает Asterisk ODBC (без pk, aors_id, reg_server).
_ENDPOINTS_VIEW_COLS = """
    e.id,
    e.transport,
    e.aors,
    e.auth,
    e.context,
    e.disallow,
    e.allow,
    e.callerid,
    CAST(e.direct_media AS CHAR) AS direct_media,
    CAST(e.rewrite_contact AS CHAR) AS rewrite_contact,
    CAST(e.rtp_symmetric AS CHAR) AS rtp_symmetric,
    CAST(e.force_rport AS CHAR) AS force_rport,
    CAST(e.trust_id_inbound AS CHAR) AS trust_id_inbound,
    CAST(e.trust_id_outbound AS CHAR) AS trust_id_outbound,
    e.mwi_from_user,
    e.mailboxes
"""

_AORS_VIEW_COLS = """
    a.id,
    a.max_contacts,
    a.minimum_expiration,
    a.default_expiration,
    a.qualify_frequency,
    CAST(a.remove_existing AS CHAR) AS remove_existing
"""

_AUTHS_VIEW_COLS = """
    au.id,
    CAST(au.auth_type AS CHAR) AS auth_type,
    au.password,
    au.username
"""


def _view_name(table: str, instance_id: int) -> str:
    if instance_id <= 0:
        raise ValueError("instance_id must be a positive integer")
    return f"{table}{PJSIP_VIEW_SUFFIX}{instance_id}"


def ps_aors_view_name(instance_id: int) -> str:
    return _view_name("ps_aors", instance_id)


def ps_endpoints_view_name(instance_id: int) -> str:
    return _view_name("ps_endpoints", instance_id)


def ps_auths_view_name(instance_id: int) -> str:
    return _view_name("ps_auths", instance_id)


def ps_endpoint_id_ips_view_name(instance_id: int) -> str:
    return _view_name("ps_endpoint_id_ips", instance_id)


def create_pjsip_views(
    db_cdr: Session,
    instance_id: int,
    reg_server: str,
) -> None:
    """Создаёт VIEW ps_*_inst_<id> без лишних колонок приложения."""
    aors_v = ps_aors_view_name(instance_id)
    endpoints_v = ps_endpoints_view_name(instance_id)
    auths_v = ps_auths_view_name(instance_id)
    id_ips_v = ps_endpoint_id_ips_view_name(instance_id)

    params = {"reg_server": reg_server}

    db_cdr.execute(
        text(
            f"""
            CREATE OR REPLACE VIEW {aors_v} AS
            SELECT {_AORS_VIEW_COLS}
            FROM ps_aors a
            WHERE a.reg_server = :reg_server
            """
        ),
        params,
    )
    db_cdr.execute(
        text(
            f"""
            CREATE OR REPLACE VIEW {endpoints_v} AS
            SELECT {_ENDPOINTS_VIEW_COLS}
            FROM ps_endpoints e
            INNER JOIN ps_aors a ON e.aors_id = a.pk
            WHERE a.reg_server = :reg_server
            """
        ),
        params,
    )
    db_cdr.execute(
        text(
            f"""
            CREATE OR REPLACE VIEW {auths_v} AS
            SELECT DISTINCT {_AUTHS_VIEW_COLS}
            FROM ps_auths au
            INNER JOIN ps_endpoints e ON e.auths_id = au.pk
            INNER JOIN ps_aors a ON e.aors_id = a.pk
            WHERE a.reg_server = :reg_server
            """
        ),
        params,
    )
    db_cdr.execute(
        text(
            f"""
            CREATE OR REPLACE VIEW {id_ips_v} AS
            SELECT i.id, i.endpoint, i.match,
                   CAST(i.srv_lookups AS CHAR) AS srv_lookups
            FROM ps_endpoint_id_ips i
            WHERE i.endpoint IN (
                SELECT e.id FROM ps_endpoints e
                INNER JOIN ps_aors a ON e.aors_id = a.pk
                WHERE a.reg_server = :reg_server
            )
            """
        ),
        params,
    )
    db_cdr.commit()


def drop_pjsip_views(db_cdr: Session, instance_id: int) -> None:
    for table in (
        "ps_aors",
        "ps_endpoints",
        "ps_auths",
        "ps_endpoint_id_ips",
    ):
        db_cdr.execute(text(f"DROP VIEW IF EXISTS {_view_name(table, instance_id)}"))
    db_cdr.commit()


def write_instance_extconfig(instance: AsteriskInstance) -> None:
    """Обновляет extconfig.conf на диске (PJSIP + static realtime через VIEW)."""
    from app.utils.ast_config_views import build_extconfig_conf

    config_dir = writable_config_dir(instance)
    if config_dir.startswith("ceph://"):
        return
    os.makedirs(config_dir, exist_ok=True)
    filepath = os.path.join(config_dir, "extconfig.conf")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(build_extconfig_conf(instance.id))
    os.chmod(filepath, 0o777)
    try:
        os.chown(filepath, config.ASTERISK_UID, config.ASTERISK_GID)
    except OSError:
        pass


def sync_pjsip_views_for_instance(
    db: Session,
    db_cdr: Session,
    instance: AsteriskInstance,
) -> None:
    """VIEW в БД, extconfig.conf и pjsip_users.conf для инстанса."""
    from app.services.instance_media import ensure_media_modules, write_musiconhold_conf
    from app.services.voicemail_modules import ensure_voicemail_modules
    from app.services.pjsip_disk_sync import write_pjsip_sorcery_conf, write_pjsip_users_conf
    from app.utils.pjsip_aor_repair import repair_aor_ids_for_instance

    repair_aor_ids_for_instance(db_cdr, instance.name)
    ensure_media_modules(instance)
    ensure_voicemail_modules(instance)
    write_musiconhold_conf(instance)
    create_pjsip_views(db_cdr, instance.id, instance.name)
    write_instance_extconfig(instance)
    write_pjsip_sorcery_conf(instance)
    write_pjsip_users_conf(instance, db_cdr)


def sync_all_pjsip_views(db: Session, db_cdr: Session) -> int:
    instances = db.query(AsteriskInstance).all()
    for instance in instances:
        sync_pjsip_views_for_instance(db, db_cdr, instance)
    return len(instances)

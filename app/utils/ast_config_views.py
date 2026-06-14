from sqlalchemy import text
from sqlalchemy.orm import Query, Session

from app.core.config import config
from app.models.ast_conf import AsteriskConf
from app.utils.ast_config_ini import STATIC_REALTIME_CONF_FILES
from app.utils.pjsip_views import (
    ps_aors_view_name,
    ps_auths_view_name,
    ps_endpoint_id_ips_view_name,
    ps_endpoints_view_name,
)

AST_CONFIG_VIEW_PREFIX = "ast_config_inst_"


def ast_config_view_name(instance_id: int) -> str:
    if instance_id <= 0:
        raise ValueError("instance_id must be a positive integer")
    return f"{AST_CONFIG_VIEW_PREFIX}{instance_id}"


def ast_conf_for_instance(db_cdr: Session, instance_id: int) -> Query:
    return db_cdr.query(AsteriskConf).filter(AsteriskConf.instance_id == instance_id)


def create_ast_config_view(db_cdr: Session, instance_id: int) -> None:
    view_name = ast_config_view_name(instance_id)
    db_cdr.execute(
        text(
            f"""
            CREATE OR REPLACE VIEW {view_name} AS
            SELECT id, cat_metric, var_metric, filename, category, var_name, var_val, commented
            FROM ast_config
            WHERE instance_id = :instance_id
            """
        ),
        {"instance_id": instance_id},
    )
    db_cdr.commit()


def drop_ast_config_view(db_cdr: Session, instance_id: int) -> None:
    view_name = ast_config_view_name(instance_id)
    db_cdr.execute(text(f"DROP VIEW IF EXISTS {view_name}"))
    db_cdr.commit()


def delete_ast_config_for_instance(db_cdr: Session, instance_id: int) -> None:
    ast_conf_for_instance(db_cdr, instance_id).delete(synchronize_session=False)
    db_cdr.commit()


def build_extconfig_conf(instance_id: int) -> str:
    """extconfig.conf: PJSIP и static realtime через VIEW инстанса."""
    ast_view = ast_config_view_name(instance_id)
    odbc_id = config.ASTERISK_ODBC_ID
    lines = [
        "[settings]",
        "; PJSIP realtime: VIEW ps_*_inst_<id> фильтруют по reg_server (имя АТС)",
        f"ps_endpoints => odbc,{odbc_id},{ps_endpoints_view_name(instance_id)}",
        f"ps_auths => odbc,{odbc_id},{ps_auths_view_name(instance_id)}",
        f"ps_aors => odbc,{odbc_id},{ps_aors_view_name(instance_id)}",
        f"; ps_contacts — базовая таблица (Asterisk пишет регистрации; VIEW не обновляем)",
        f"ps_contacts => odbc,{odbc_id},ps_contacts",
        f"ps_endpoint_id_ips => odbc,{odbc_id},{ps_endpoint_id_ips_view_name(instance_id)}",
        f"ps_domain_aliases => odbc,{odbc_id},ps_domain_aliases",
        "",
        f"; static realtime: VIEW {ast_view} фильтрует строки по instance_id",
    ]
    for filename in STATIC_REALTIME_CONF_FILES:
        lines.append(f"{filename} => odbc,{odbc_id},{ast_view}")
    return "\n".join(lines) + "\n"

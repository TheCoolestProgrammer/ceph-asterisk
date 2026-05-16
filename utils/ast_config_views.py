from sqlalchemy import text
from sqlalchemy.orm import Query, Session

from models.ast_conf import AsteriskConf

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

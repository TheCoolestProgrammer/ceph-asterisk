"""Список контекстов диалплана (extensions.conf) для UI и PJSIP."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ast_conf import AsteriskConf


def list_dialplan_contexts(
    db_cdr: Session,
    instance_id: int,
    filename: str = "extensions.conf",
    *,
    include_commented: bool = False,
) -> list[str]:
    """Уникальные category из ast_config, без системных контекстов Asterisk (__*)."""
    query = db_cdr.query(AsteriskConf.category).filter(
        AsteriskConf.instance_id == instance_id,
        AsteriskConf.filename == filename,
    )
    if not include_commented:
        query = query.filter(AsteriskConf.commented == 0)

    rows = (
        query.group_by(AsteriskConf.category)
        .order_by(func.min(AsteriskConf.cat_metric))
        .all()
    )
    return [
        category
        for (category,) in rows
        if category and not category.startswith("__")
    ]

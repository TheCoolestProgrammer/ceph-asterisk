"""Исправление устаревшего внутреннего диалплана (Echo вместо Dial)."""

from sqlalchemy.orm import Session

from app.models.ast_conf import AsteriskConf


def repair_internal_dialplan(db_cdr: Session, instance_id: int) -> bool:
    """
    Заменяет Echo()/Playback на Dial(PJSIP/${EXTEN}) в extensions.conf.
    Возвращает True, если были изменения.
    """
    changed = False

    echo_rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == "extensions.conf",
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like("%Echo()%"),
        )
        .all()
    )
    for row in echo_rows:
        row.var_val = "_XXX,n,Dial(PJSIP/${EXTEN},20)"
        changed = True

    stale_rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == "extensions.conf",
            AsteriskConf.var_name == "exten",
        )
        .filter(
            (AsteriskConf.var_val.like("%Playback%"))
            | (AsteriskConf.var_val == "_XXX,n,Answer()")
        )
        .all()
    )
    for row in stale_rows:
        db_cdr.delete(row)
        changed = True

    if changed:
        db_cdr.commit()
    return changed


def repair_queue_and_moh(db_cdr: Session, instance_id: int) -> bool:
    """Убирает лишний MusicOnHold перед Queue; добавляет member PJSIP/102."""
    changed = False

    for row in (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == "extensions.conf",
            AsteriskConf.var_val.like("%MusicOnHold%"),
        )
        .all()
    ):
        db_cdr.delete(row)
        changed = True

    has_102 = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == "queues.conf",
            AsteriskConf.var_val == "PJSIP/102",
        )
        .first()
    )
    if not has_102:
        max_cat = (
            db_cdr.query(AsteriskConf.cat_metric)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == "queues.conf",
                AsteriskConf.category == "test-support",
            )
            .order_by(AsteriskConf.cat_metric.desc())
            .limit(1)
            .scalar()
        ) or 1
        max_var = (
            db_cdr.query(AsteriskConf.var_metric)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == "queues.conf",
                AsteriskConf.category == "test-support",
            )
            .order_by(AsteriskConf.var_metric.desc())
            .limit(1)
            .scalar()
        ) or 0
        db_cdr.add(
            AsteriskConf(
                instance_id=instance_id,
                filename="queues.conf",
                category="test-support",
                var_name="member",
                var_val="PJSIP/102",
                cat_metric=max_cat,
                var_metric=max_var + 1,
            )
        )
        changed = True

    if changed:
        db_cdr.commit()
    return changed

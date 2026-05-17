"""Диалплан для Asterisk voicemail: запись при недозвоне и *97 для софтфона."""

from sqlalchemy.orm import Session

from models.ast_conf import AsteriskConf

EXTENSIONS_FILENAME = "extensions.conf"


def _next_metrics(
    db_cdr: Session, instance_id: int, category: str
) -> tuple[int, int]:
    max_cat = (
        db_cdr.query(AsteriskConf.cat_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
        )
        .order_by(AsteriskConf.cat_metric.desc())
        .limit(1)
        .scalar()
    )
    max_var = (
        db_cdr.query(AsteriskConf.var_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
        )
        .order_by(AsteriskConf.var_metric.desc())
        .limit(1)
        .scalar()
    )
    return (max_cat or 0) + 1, (max_var or 0)


def _has_exten_pattern(
    db_cdr: Session, instance_id: int, category: str, pattern: str
) -> bool:
    return (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like(f"{pattern},%"),
        )
        .first()
        is not None
    )


def _insert_exten_rows(
    db_cdr: Session,
    instance_id: int,
    category: str,
    cat_metric: int,
    lines: list[str],
    start_var_metric: int = 0,
) -> None:
    var_metric = start_var_metric
    for line in lines:
        var_metric += 1
        db_cdr.add(
            AsteriskConf(
                instance_id=instance_id,
                filename=EXTENSIONS_FILENAME,
                category=category,
                var_name="exten",
                var_val=line,
                cat_metric=cat_metric,
                var_metric=var_metric,
            )
        )


def ensure_voicemail_dialplan(db_cdr: Session, instance_id: int) -> bool:
    """
    Добавляет *97 (VoiceMailMain) и перевод на VoiceMail после неудачного Dial.
    Возвращает True, если были изменения.
    """
    changed = False

    if not _has_exten_pattern(db_cdr, instance_id, "from-internal", "*97"):
        cat_metric, _ = _next_metrics(db_cdr, instance_id, "from-internal")
        _insert_exten_rows(
            db_cdr,
            instance_id,
            "from-internal",
            cat_metric,
            [
                "*97,1,NoOp(Доступ к голосовой почте)",
                "*97,n,VoiceMailMain(${CALLERID(num)}@default)",
                "*97,n,Hangup()",
            ],
        )
        changed = True

    if not _has_exten_pattern(db_cdr, instance_id, "from-internal", "_XXX"):
        return changed

    has_vm = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == "from-internal",
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like("_XXX,%"),
            AsteriskConf.var_val.like("%VoiceMail%"),
        )
        .first()
    )
    if has_vm:
        return changed

    xxx_rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == "from-internal",
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like("_XXX,%"),
        )
        .order_by(AsteriskConf.var_metric)
        .all()
    )
    if not xxx_rows:
        return changed

    cat_metric = xxx_rows[0].cat_metric
    max_var = max(row.var_metric for row in xxx_rows)

    for row in xxx_rows:
        if row.var_val.endswith(",Hangup()") and "Dial(" in row.var_val:
            db_cdr.delete(row)
            changed = True
        elif row.var_val.endswith(",Hangup()") and "Dial(" not in row.var_val:
            db_cdr.delete(row)
            changed = True

    _insert_exten_rows(
        db_cdr,
        instance_id,
        "from-internal",
        cat_metric,
        [
            '_XXX,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?vm_done)',
            "_XXX,n,VoiceMail(${EXTEN}@default,u)",
            "_XXX,n(vm_done),Hangup()",
        ],
        start_var_metric=max_var,
    )
    changed = True

    if _has_exten_pattern(db_cdr, instance_id, "from-external", "777"):
        has_ext_vm = (
            db_cdr.query(AsteriskConf)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == EXTENSIONS_FILENAME,
                AsteriskConf.category == "from-external",
                AsteriskConf.var_name == "exten",
                AsteriskConf.var_val.like("777,%"),
                AsteriskConf.var_val.like("%VoiceMail%"),
            )
            .first()
        )
        if not has_ext_vm:
            ext_rows = (
                db_cdr.query(AsteriskConf)
                .filter(
                    AsteriskConf.instance_id == instance_id,
                    AsteriskConf.filename == EXTENSIONS_FILENAME,
                    AsteriskConf.category == "from-external",
                    AsteriskConf.var_name == "exten",
                    AsteriskConf.var_val.like("777,%"),
                )
                .order_by(AsteriskConf.var_metric)
                .all()
            )
            if ext_rows:
                cat_metric = ext_rows[0].cat_metric
                max_var = max(row.var_metric for row in ext_rows)
                for row in ext_rows:
                    if row.var_val.endswith(",Hangup()"):
                        db_cdr.delete(row)
                        changed = True
                _insert_exten_rows(
                    db_cdr,
                    instance_id,
                    "from-external",
                    cat_metric,
                    [
                        '777,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?ext_done)',
                        "777,n,VoiceMail(101@default,u)",
                        "777,n(ext_done),Hangup()",
                    ],
                    start_var_metric=max_var,
                )
                changed = True

    if changed:
        db_cdr.commit()
    return changed

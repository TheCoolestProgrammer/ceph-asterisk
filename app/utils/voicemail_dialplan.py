"""Диалплан для Asterisk voicemail: запись при недозвоне и доступ с софтфона."""

from sqlalchemy.orm import Session

from app.models.ast_conf import AsteriskConf

EXTENSIONS_FILENAME = "extensions.conf"

VM_CONTEXTS = ("from-internal", "from-external")

# ODBC realtime (res_config_odbc): при смене cat_metric внутри одного [context]
# создаётся отдельный блок — в диалплан попадает только один из них.
# Все exten одного контекста должны иметь один cat_metric, различаться var_metric.

FULL_777_REQUIRED_FRAGMENTS = (
    "777,n,Answer()",
    "777,n,Dial(PJSIP/101",
    '777,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?',
    "777,n,NoOp(777 VM DIALSTATUS=${DIALSTATUS})",
    "777,n,VoiceMail(101@default)",
)


def _full_777_lines(done_label: str, noop: str) -> list[str]:
    return [
        f"777,1,NoOp({noop})",
        "777,n,Answer()",
        "777,n,Dial(PJSIP/101,30)",
        f'777,n,GotoIf($["${{DIALSTATUS}}"="ANSWER"]?{done_label})',
        '777,n,NoOp(777 VM DIALSTATUS=${DIALSTATUS})',
        "777,n,VoiceMail(101@default)",
        "777,n,Hangup()",
        f"777,n({done_label}),Hangup()",
    ]


INTERNAL_777_LINES = _full_777_lines(
    "int777_done", "Сервис 777 от ${CALLERID(num)}"
)
EXTERNAL_777_LINES = _full_777_lines(
    "ext777_done", "Входящий на 777 от ${CALLERID(all)}"
)


def _vm_access_lines(exten: str) -> list[str]:
    return [
        f"{exten},1,NoOp(Голосовая почта ${{CALLERID(num)}})",
        f"{exten},n,Answer()",
        f"{exten},n,Wait(1)",
        f"{exten},n,Set(VMBOX=${{CALLERID(num)}})",
        f'{exten},n,GotoIf($[${{REGEX("^[0-9]+$" ${{VMBOX}})}}]?vm_login:vm_prompt)',
        f"{exten},n(vm_prompt),VoiceMailMain(@default)",
        f"{exten},n,Hangup()",
        f"{exten},n(vm_login),VoiceMailMain(${{VMBOX}}@default)",
        f"{exten},n,Hangup()",
    ]


VM_ACCESS_EXTENSIONS: tuple[tuple[str, list[str]], ...] = (
    ("*97", _vm_access_lines("*97")),
    ("8097", _vm_access_lines("8097")),
)


def _context_cat_metric(db_cdr: Session, instance_id: int, category: str) -> int:
    """Единый cat_metric для всех exten в [context]."""
    existing = (
        db_cdr.query(AsteriskConf.cat_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
        )
        .order_by(AsteriskConf.cat_metric.asc())
        .limit(1)
        .scalar()
    )
    if existing is not None:
        return existing

    max_cat = (
        db_cdr.query(AsteriskConf.cat_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
        )
        .order_by(AsteriskConf.cat_metric.desc())
        .limit(1)
        .scalar()
    )
    return (max_cat or 0) + 1


def _next_var_metric(db_cdr: Session, instance_id: int, category: str) -> int:
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
    return max_var or 0


def _normalize_context_cat_metric(
    db_cdr: Session, instance_id: int, category: str
) -> bool:
    """Сводит все строки extensions.conf контекста к одному cat_metric."""
    rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
            AsteriskConf.var_name == "exten",
        )
        .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
        .all()
    )
    if not rows:
        return False

    cat_metrics = {row.cat_metric for row in rows}
    if len(cat_metrics) <= 1:
        return False

    target_cat = min(cat_metrics)
    changed = False
    for var_metric, row in enumerate(rows, start=1):
        if row.cat_metric != target_cat:
            row.cat_metric = target_cat
            changed = True
        if row.var_metric != var_metric:
            row.var_metric = var_metric
            changed = True
    return changed


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


def _delete_exten_pattern(
    db_cdr: Session, instance_id: int, category: str, pattern: str
) -> int:
    return (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like(f"{pattern},%"),
        )
        .delete(synchronize_session=False)
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


def _777_has_exact_lines(
    db_cdr: Session, instance_id: int, category: str, lines: list[str]
) -> bool:
    for line in lines:
        if not (
            db_cdr.query(AsteriskConf)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == EXTENSIONS_FILENAME,
                AsteriskConf.category == category,
                AsteriskConf.var_name == "exten",
                AsteriskConf.var_val == line,
            )
            .first()
        ):
            return False
    return True


def _777_is_complete(
    db_cdr: Session, instance_id: int, category: str, expected_lines: list[str]
) -> bool:
    if not _has_exten_pattern(db_cdr, instance_id, category, "777"):
        return False
    for fragment in FULL_777_REQUIRED_FRAGMENTS:
        if not (
            db_cdr.query(AsteriskConf)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == EXTENSIONS_FILENAME,
                AsteriskConf.category == category,
                AsteriskConf.var_name == "exten",
                AsteriskConf.var_val.like(f"%{fragment}%"),
            )
            .first()
        ):
            return False
    old_style = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == category,
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like("777,%"),
        )
        .filter(
            (AsteriskConf.var_val.like("%VoiceMail(101@default,u)%"))
            | (AsteriskConf.var_val.like("%VoiceMail(101@default,b)%"))
        )
        .first()
    )
    if old_style is not None:
        return False
    return _777_has_exact_lines(db_cdr, instance_id, category, expected_lines)


def _ensure_777_in_context(
    db_cdr: Session, instance_id: int, category: str, lines: list[str]
) -> bool:
    if _777_is_complete(db_cdr, instance_id, category, lines):
        return False

    cat_metric = _context_cat_metric(db_cdr, instance_id, category)
    _delete_exten_pattern(db_cdr, instance_id, category, "777")
    start_var = _next_var_metric(db_cdr, instance_id, category)
    _insert_exten_rows(
        db_cdr, instance_id, category, cat_metric, lines, start_var_metric=start_var
    )
    return True


def _vm_access_is_complete(
    db_cdr: Session, instance_id: int, category: str, lines: list[str]
) -> bool:
    for line in lines:
        if not (
            db_cdr.query(AsteriskConf)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == EXTENSIONS_FILENAME,
                AsteriskConf.category == category,
                AsteriskConf.var_name == "exten",
                AsteriskConf.var_val == line,
            )
            .first()
        ):
            return False
    return True


def _ensure_vm_access_codes(db_cdr: Session, instance_id: int) -> bool:
    changed = False
    for context in VM_CONTEXTS:
        cat_metric = _context_cat_metric(db_cdr, instance_id, context)
        for exten, lines in VM_ACCESS_EXTENSIONS:
            if _vm_access_is_complete(db_cdr, instance_id, context, lines):
                continue
            _delete_exten_pattern(db_cdr, instance_id, context, exten)
            start_var = _next_var_metric(db_cdr, instance_id, context)
            _insert_exten_rows(
                db_cdr,
                instance_id,
                context,
                cat_metric,
                lines,
                start_var_metric=start_var,
            )
            changed = True
    return changed


def _ensure_xxx_voicemail(db_cdr: Session, instance_id: int) -> bool:
    if not _has_exten_pattern(db_cdr, instance_id, "from-internal", "_XXX"):
        return False

    has_new = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == "from-internal",
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val == "_XXX,n,VoiceMail(${EXTEN}@default)",
        )
        .first()
    )
    if has_new:
        return False

    cat_metric = _context_cat_metric(db_cdr, instance_id, "from-internal")
    xxx_rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == EXTENSIONS_FILENAME,
            AsteriskConf.category == "from-internal",
            AsteriskConf.var_name == "exten",
            AsteriskConf.var_val.like("_XXX,%"),
        )
        .all()
    )
    for row in xxx_rows:
        val = row.var_val
        if (
            val.endswith(",Hangup()")
            or "VoiceMail" in val
            or "GotoIf" in val
            or "vm_done" in val
            or "vm_busy" in val
        ):
            db_cdr.delete(row)

    start_var = _next_var_metric(db_cdr, instance_id, "from-internal")
    _insert_exten_rows(
        db_cdr,
        instance_id,
        "from-internal",
        cat_metric,
        [
            '_XXX,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?vm_done)',
            '_XXX,n,NoOp(internal VM DIALSTATUS=${DIALSTATUS})',
            "_XXX,n,VoiceMail(${EXTEN}@default)",
            "_XXX,n,Hangup()",
            "_XXX,n(vm_done),Hangup()",
        ],
        start_var_metric=start_var,
    )
    return True


def ensure_voicemail_dialplan(db_cdr: Session, instance_id: int) -> bool:
    """Обновляет диалплан voicemail; нормализует cat_metric для ODBC realtime."""
    changed = False

    for context in VM_CONTEXTS:
        if _normalize_context_cat_metric(db_cdr, instance_id, context):
            changed = True

    if _ensure_vm_access_codes(db_cdr, instance_id):
        changed = True
    if _ensure_777_in_context(
        db_cdr, instance_id, "from-internal", INTERNAL_777_LINES
    ):
        changed = True
    if _ensure_777_in_context(
        db_cdr, instance_id, "from-external", EXTERNAL_777_LINES
    ):
        changed = True
    if _ensure_xxx_voicemail(db_cdr, instance_id):
        changed = True

    for context in VM_CONTEXTS:
        if _normalize_context_cat_metric(db_cdr, instance_id, context):
            changed = True

    if changed:
        db_cdr.commit()
    return changed

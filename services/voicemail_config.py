"""CRUD голосовых ящиков Asterisk в static realtime (ast_config / voicemail.conf)."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from models.ast_conf import AsteriskConf
from models.sip_user import PjsipAor, PjsipEndpoint
from schemas.voicemail import (
    DEFAULT_VM_CONTEXT,
    RESERVED_VM_CONTEXTS,
    VoicemailCreate,
    VoicemailResponse,
    VoicemailUpdate,
)
from services.voicemail_modules import ensure_voicemail_modules
from utils.voicemail_dialplan import ensure_voicemail_dialplan

VOICEMAIL_CONF_FILENAME = "voicemail.conf"

GENERAL_VOICEMAIL_OPTIONS: tuple[tuple[str, str], ...] = (
    ("format", "wav49|gsm|wav"),
    ("serveremail", "asterisk"),
    ("attach", "yes"),
    ("skipms", "3000"),
    ("maxsilence", "10"),
    ("minmessage", "1"),
    ("maxmessage", "300"),
    ("sendvoicemail", "yes"),
    ("review", "yes"),
)


def _format_mailbox_val(password: str, full_name: str, email: str | None) -> str:
    if email:
        return f"{password},{full_name},{email}"
    return f"{password},{full_name}"


def _parse_mailbox_val(var_val: str) -> tuple[str, str, str | None]:
    parts = [part.strip() for part in var_val.split(",", 2)]
    password = parts[0] if parts else ""
    full_name = parts[1] if len(parts) > 1 else ""
    email = parts[2] if len(parts) > 2 and parts[2] else None
    return password, full_name, email


def _mailbox_rows_filter(
    db_cdr: Session, instance_id: int, context: str | None = None, mailbox: str | None = None
):
    query = db_cdr.query(AsteriskConf).filter(
        AsteriskConf.instance_id == instance_id,
        AsteriskConf.filename == VOICEMAIL_CONF_FILENAME,
    )
    if context is not None:
        query = query.filter(AsteriskConf.category == context)
    if mailbox is not None:
        query = query.filter(AsteriskConf.var_name == mailbox)
    return query


def _is_mailbox_category(category: str) -> bool:
    return category.lower() not in RESERVED_VM_CONTEXTS


def _row_to_response(row: AsteriskConf) -> VoicemailResponse:
    password, full_name, email = _parse_mailbox_val(row.var_val)
    return VoicemailResponse(
        mailbox=row.var_name,
        context=row.category,
        password=password,
        full_name=full_name,
        email=email,
    )


def _general_exists(db_cdr: Session, instance_id: int) -> bool:
    return (
        _mailbox_rows_filter(db_cdr, instance_id, context="general")
        .limit(1)
        .first()
        is not None
    )


def _ensure_general_section(db_cdr: Session, instance_id: int) -> None:
    if _general_exists(db_cdr, instance_id):
        return
    cat_metric = 1
    for var_metric, (var_name, var_val) in enumerate(GENERAL_VOICEMAIL_OPTIONS, start=1):
        db_cdr.add(
            AsteriskConf(
                instance_id=instance_id,
                filename=VOICEMAIL_CONF_FILENAME,
                category="general",
                var_name=var_name,
                var_val=var_val,
                cat_metric=cat_metric,
                var_metric=var_metric,
            )
        )


def _next_context_cat_metric(db_cdr: Session, instance_id: int) -> int:
    max_metric = (
        db_cdr.query(AsteriskConf.cat_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == VOICEMAIL_CONF_FILENAME,
        )
        .order_by(AsteriskConf.cat_metric.desc())
        .limit(1)
        .scalar()
    )
    return (max_metric or 0) + 1


def _link_endpoint_mwi(
    cdr_db: Session,
    instance_name: str,
    mailbox: str,
    context: str,
    *,
    enable: bool,
) -> bool:
    endpoint = (
        cdr_db.query(PjsipEndpoint)
        .options(joinedload(PjsipEndpoint.aors_fk))
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)
        .filter(PjsipAor.reg_server == instance_name)
        .filter(PjsipEndpoint.id == mailbox)
        .first()
    )
    if not endpoint:
        return False
    endpoint.mailboxes = f"{mailbox}@{context}" if enable else None
    return True


def list_voicemail_boxes(db_cdr: Session, instance_id: int) -> list[VoicemailResponse]:
    rows = (
        _mailbox_rows_filter(db_cdr, instance_id)
        .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
        .all()
    )
    return [
        _row_to_response(row)
        for row in rows
        if _is_mailbox_category(row.category)
    ]


def get_voicemail_box(
    db_cdr: Session, instance_id: int, mailbox: str, context: str = DEFAULT_VM_CONTEXT
) -> VoicemailResponse | None:
    row = (
        _mailbox_rows_filter(db_cdr, instance_id, context=context, mailbox=mailbox)
        .first()
    )
    if not row:
        return None
    return _row_to_response(row)


def mailbox_exists(
    db_cdr: Session, instance_id: int, mailbox: str, context: str = DEFAULT_VM_CONTEXT
) -> bool:
    return get_voicemail_box(db_cdr, instance_id, mailbox, context) is not None


def create_voicemail_box(
    db_cdr: Session,
    instance_id: int,
    instance_name: str,
    data: VoicemailCreate,
    *,
    instance=None,
) -> VoicemailResponse:
    if mailbox_exists(db_cdr, instance_id, data.mailbox, data.context):
        raise ValueError(
            f"Voicemail box '{data.mailbox}@{data.context}' already exists"
        )

    _ensure_general_section(db_cdr, instance_id)

    cat_metric = (
        db_cdr.query(AsteriskConf.cat_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == VOICEMAIL_CONF_FILENAME,
            AsteriskConf.category == data.context,
        )
        .limit(1)
        .scalar()
    )
    if cat_metric is None:
        cat_metric = _next_context_cat_metric(db_cdr, instance_id)

    max_var = (
        db_cdr.query(AsteriskConf.var_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == VOICEMAIL_CONF_FILENAME,
            AsteriskConf.category == data.context,
        )
        .order_by(AsteriskConf.var_metric.desc())
        .limit(1)
        .scalar()
    ) or 0

    row = AsteriskConf(
        instance_id=instance_id,
        filename=VOICEMAIL_CONF_FILENAME,
        category=data.context,
        var_name=data.mailbox,
        var_val=_format_mailbox_val(data.password, data.full_name, data.email),
        cat_metric=cat_metric,
        var_metric=max_var + 1,
    )
    db_cdr.add(row)

    if data.link_endpoint_mwi:
        _link_endpoint_mwi(
            db_cdr,
            instance_name,
            data.mailbox,
            data.context,
            enable=True,
        )

    ensure_voicemail_dialplan(db_cdr, instance_id)
    if instance is not None:
        ensure_voicemail_modules(instance)

    db_cdr.commit()
    db_cdr.refresh(row)
    return _row_to_response(row)


def update_voicemail_box(
    db_cdr: Session,
    instance_id: int,
    mailbox: str,
    data: VoicemailUpdate,
    context: str = DEFAULT_VM_CONTEXT,
) -> VoicemailResponse:
    row = (
        _mailbox_rows_filter(db_cdr, instance_id, context=context, mailbox=mailbox)
        .first()
    )
    if not row:
        raise LookupError(f"Voicemail box '{mailbox}@{context}' not found")

    password, full_name, email = _parse_mailbox_val(row.var_val)
    if data.password is not None:
        password = data.password
    if data.full_name is not None:
        full_name = data.full_name
    if data.email is not None:
        email = data.email or None

    row.var_val = _format_mailbox_val(password, full_name, email)
    db_cdr.commit()
    db_cdr.refresh(row)
    return _row_to_response(row)


def delete_voicemail_box(
    db_cdr: Session,
    instance_id: int,
    instance_name: str,
    mailbox: str,
    context: str = DEFAULT_VM_CONTEXT,
    *,
    clear_endpoint_mwi: bool = True,
) -> bool:
    deleted = _mailbox_rows_filter(
        db_cdr, instance_id, context=context, mailbox=mailbox
    ).delete(synchronize_session=False)
    if not deleted:
        return False
    if clear_endpoint_mwi:
        _link_endpoint_mwi(
            cdr_db=db_cdr,
            instance_name=instance_name,
            mailbox=mailbox,
            context=context,
            enable=False,
        )
    db_cdr.commit()
    return True


def seed_test_voicemail_boxes(
    db_cdr: Session,
    instance_id: int,
    instance_name: str,
    *,
    instance=None,
) -> list[str]:
    """Создаёт тестовые ящики 101 и 102, если их ещё нет."""
    created: list[str] = []
    test_boxes = (
        VoicemailCreate(
            mailbox="101",
            password="4242",
            full_name="Test Operator 101",
            link_endpoint_mwi=True,
        ),
        VoicemailCreate(
            mailbox="102",
            password="4242",
            full_name="Test Operator 102",
            link_endpoint_mwi=True,
        ),
    )
    for box in test_boxes:
        if mailbox_exists(db_cdr, instance_id, box.mailbox, box.context):
            if box.link_endpoint_mwi:
                _link_endpoint_mwi(
                    db_cdr, instance_name, box.mailbox, box.context, enable=True
                )
            continue
        create_voicemail_box(
            db_cdr, instance_id, instance_name, box, instance=instance
        )
        created.append(box.mailbox)
    if not created and instance is not None:
        ensure_voicemail_dialplan(db_cdr, instance_id)
        ensure_voicemail_modules(instance)
        db_cdr.commit()
    return created

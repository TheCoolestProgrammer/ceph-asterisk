from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.ast_conf import AsteriskConf
from app.models.asterisk_instance import AsteriskInstance
from app.models.sip_user import PjsipAor, PjsipEndpoint
from app.schemas.voicemail import (
    DEFAULT_VM_CONTEXT,
    RESERVED_VM_CONTEXTS,
    VoicemailCreate,
    VoicemailResponse,
    VoicemailUpdate,
)
from app.services.voicemail_modules import ensure_voicemail_modules
from app.utils.instance_voicemail_spool import ensure_mailbox_voicemail_dir

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


def get_test_voicemail_boxes() -> tuple[VoicemailCreate, ...]:
    """Возвращает набор тестовых voicemail ящиков."""
    return (
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
    db_cdr: Session,
    instance_id: int,
    context: str | None = None,
    mailbox: str | None = None,
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
        _mailbox_rows_filter(db_cdr, instance_id, context="general").limit(1).first()
        is not None
    )


def _ensure_general_section(db_cdr: Session, instance_id: int) -> None:
    if _general_exists(db_cdr, instance_id):
        return
    cat_metric = 1
    for var_metric, (var_name, var_val) in enumerate(
        GENERAL_VOICEMAIL_OPTIONS, start=1
    ):
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


def _get_endpoint_for_instance(
    cdr_db: Session, instance_name: str, user_id: str
) -> PjsipEndpoint | None:
    return (
        cdr_db.query(PjsipEndpoint)
        .options(joinedload(PjsipEndpoint.aors_fk))
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)
        .filter(PjsipAor.reg_server == instance_name)
        .filter(PjsipEndpoint.id == user_id)
        .first()
    )


def _parse_endpoint_mailbox_ref(mailboxes: str | None) -> tuple[str, str] | None:
    if not mailboxes:
        return None
    first_ref = mailboxes.split(",", 1)[0].strip()
    if not first_ref:
        return None
    if "@" in first_ref:
        mailbox, context = first_ref.split("@", 1)
        mailbox = mailbox.strip()
        context = context.strip() or DEFAULT_VM_CONTEXT
    else:
        mailbox = first_ref
        context = DEFAULT_VM_CONTEXT
    if not mailbox:
        return None
    return mailbox, context


def _parse_mailbox_refs(mailboxes: str | None) -> list[tuple[str, str]]:
    if not mailboxes:
        return []
    refs: list[tuple[str, str]] = []
    for raw_ref in mailboxes.split(","):
        ref = raw_ref.strip()
        if not ref:
            continue
        if "@" in ref:
            mailbox, context = ref.split("@", 1)
            mailbox = mailbox.strip()
            context = context.strip() or DEFAULT_VM_CONTEXT
        else:
            mailbox = ref
            context = DEFAULT_VM_CONTEXT
        if mailbox:
            refs.append((mailbox, context))
    return refs


def _format_mailbox_refs(refs: list[tuple[str, str]]) -> str | None:
    if not refs:
        return None
    formatted = [
        f"{mailbox}@{context}" if context else f"{mailbox}@{DEFAULT_VM_CONTEXT}"
        for mailbox, context in refs
    ]
    return ",".join(formatted)


def list_voicemail_boxes(db_cdr: Session, instance_id: int) -> list[VoicemailResponse]:
    rows = (
        _mailbox_rows_filter(db_cdr, instance_id)
        .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
        .all()
    )
    return [_row_to_response(row) for row in rows if _is_mailbox_category(row.category)]


def get_voicemail_box(
    db_cdr: Session, instance_id: int, mailbox: str, context: str = DEFAULT_VM_CONTEXT
) -> VoicemailResponse | None:
    row = _mailbox_rows_filter(
        db_cdr, instance_id, context=context, mailbox=mailbox
    ).first()
    if not row:
        return None
    return _row_to_response(row)


def mailbox_exists(
    db_cdr: Session, instance_id: int, mailbox: str, context: str = DEFAULT_VM_CONTEXT
) -> bool:
    return get_voicemail_box(db_cdr, instance_id, mailbox, context) is not None


def get_voicemail_box_by_user_id(
    db_cdr: Session, instance_id: int, instance_name: str, user_id: str
) -> VoicemailResponse | None:
    endpoint = _get_endpoint_for_instance(db_cdr, instance_name, user_id)
    if endpoint is None:
        return None

    mailbox_ref = _parse_endpoint_mailbox_ref(endpoint.mailboxes)
    if mailbox_ref is not None:
        mailbox, context = mailbox_ref
        box = get_voicemail_box(db_cdr, instance_id, mailbox, context)
        if box is not None:
            return box

    return None


def bind_user_to_voicemail_box(
    db_cdr: Session,
    instance_id: int,
    instance_name: str,
    *,
    user_id: str,
    mailbox: str,
    context: str = DEFAULT_VM_CONTEXT,
) -> tuple[str, str, str]:
    endpoint = _get_endpoint_for_instance(db_cdr, instance_name, user_id)
    if endpoint is None:
        raise LookupError(f"User '{user_id}' not found in instance '{instance_name}'")

    box = get_voicemail_box(db_cdr, instance_id, mailbox, context)
    if box is None:
        raise LookupError(f"Voicemail box '{mailbox}@{context}' not found")

    endpoint.mailboxes = f"{mailbox}@{context}"
    db_cdr.commit()
    return user_id, mailbox, context


def unbind_user_from_voicemail_box(
    db_cdr: Session,
    instance_name: str,
    *,
    user_id: str,
    mailbox: str | None = None,
    context: str = DEFAULT_VM_CONTEXT,
) -> tuple[str, str | None, str]:
    endpoint = _get_endpoint_for_instance(db_cdr, instance_name, user_id)
    if endpoint is None:
        raise LookupError(f"User '{user_id}' not found in instance '{instance_name}'")

    refs = _parse_mailbox_refs(endpoint.mailboxes)
    if mailbox is None:
        endpoint.mailboxes = None
        db_cdr.commit()
        return user_id, None, context

    filtered = [
        (ref_mailbox, ref_context)
        for ref_mailbox, ref_context in refs
        if not (ref_mailbox == mailbox and ref_context == context)
    ]
    endpoint.mailboxes = _format_mailbox_refs(filtered)
    db_cdr.commit()
    return user_id, mailbox, context


def unbind_mailbox_from_all_users(
    db_cdr: Session, instance_name: str, mailbox: str, context: str
) -> int:
    endpoints = (
        db_cdr.query(PjsipEndpoint)
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)
        .filter(PjsipAor.reg_server == instance_name)
        .all()
    )
    unlinked_count = 0
    for endpoint in endpoints:
        refs = _parse_mailbox_refs(endpoint.mailboxes)
        if not refs:
            continue
        filtered = [
            (ref_mailbox, ref_context)
            for ref_mailbox, ref_context in refs
            if not (ref_mailbox == mailbox and ref_context == context)
        ]
        if len(filtered) == len(refs):
            continue
        endpoint.mailboxes = _format_mailbox_refs(filtered)
        unlinked_count += 1
    return unlinked_count


def create_voicemail_box(
    db_cdr: Session,
    instance_id: int,
    instance_name: str,
    data: VoicemailCreate,
    *,
    instance=None,
    db=None,
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

    if instance is not None:
        ensure_voicemail_modules(instance)

    db_cdr.commit()
    db_cdr.refresh(row)

    # Создаём папки для mailbox'a на диске
    if instance is None and db is not None:
        instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.id == instance_id)
            .first()
        )
    if instance is not None:
        ensure_mailbox_voicemail_dir(instance, data.mailbox, context=data.context)

    return _row_to_response(row)


def update_voicemail_box(
    db_cdr: Session,
    instance_id: int,
    mailbox: str,
    data: VoicemailUpdate,
    context: str = DEFAULT_VM_CONTEXT,
) -> VoicemailResponse:
    row = _mailbox_rows_filter(
        db_cdr, instance_id, context=context, mailbox=mailbox
    ).first()
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
        unbind_mailbox_from_all_users(db_cdr, instance_name, mailbox, context)
    db_cdr.commit()
    return True


def seed_test_voicemail_boxes(
    db_cdr: Session,
    instance_id: int,
    instance_name: str,
    *,
    instance=None,
    test_boxes: tuple[VoicemailCreate, ...] | None = None,
) -> list[str]:
    """Создаёт voicemail ящики, если их ещё нет.

    Args:
        db_cdr: Сессия базы данных
        instance_id: ID экземпляра АТС
        instance_name: Имя экземпляра АТС
        instance: Экземпляр АТС (опционально)
        test_boxes: Кортеж с данными voicemail ящиков. По умолчанию None (пустой список)
    """
    created: list[str] = []

    # Если тестовые данные не переданы, используем пустой список
    boxes_to_create = test_boxes if test_boxes is not None else ()

    for box in boxes_to_create:
        if mailbox_exists(db_cdr, instance_id, box.mailbox, box.context):
            if box.link_endpoint_mwi:
                _link_endpoint_mwi(
                    db_cdr, instance_name, box.mailbox, box.context, enable=True
                )
            continue
        create_voicemail_box(db_cdr, instance_id, instance_name, box, instance=instance)
        created.append(box.mailbox)
    if not created and instance is not None:
        ensure_voicemail_modules(instance)
        db_cdr.commit()
    return created

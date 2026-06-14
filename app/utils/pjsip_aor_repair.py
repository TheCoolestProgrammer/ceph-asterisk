"""Исправление id AOR: REGISTER в Asterisk требует AOR = user из To: (101, не 101-aor)."""

from sqlalchemy.orm import Session

from app.models.sip_user import PjsipAor, PjsipEndpoint


def repair_aor_ids_for_instance(db_cdr: Session, reg_server: str) -> list[str]:
    """
    Переименовывает ps_aors.id и ps_endpoints.aors: 101-aor -> 101.
    Возвращает список исправленных extension.
    """
    fixed: list[str] = []
    suffix = "-aor"

    aors = (
        db_cdr.query(PjsipAor)
        .filter(PjsipAor.reg_server == reg_server, PjsipAor.id.like(f"%{suffix}"))
        .all()
    )
    for aor in aors:
        if not aor.id.endswith(suffix):
            continue
        new_id = aor.id[: -len(suffix)]
        conflict = (
            db_cdr.query(PjsipAor)
            .filter(PjsipAor.reg_server == reg_server, PjsipAor.id == new_id)
            .first()
        )
        if conflict and conflict.pk != aor.pk:
            continue
        aor.id = new_id
        fixed.append(new_id)

    if not fixed:
        return []

    endpoints = (
        db_cdr.query(PjsipEndpoint)
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)
        .filter(PjsipAor.reg_server == reg_server)
        .all()
    )
    for ep in endpoints:
        if ep.aors and ep.aors.endswith(suffix):
            ep.aors = ep.aors[: -len(suffix)]

    db_cdr.commit()
    return sorted(set(fixed))

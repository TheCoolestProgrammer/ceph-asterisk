"""Создание тестовых PJSIP-пользователей при создании АТС."""

from sqlalchemy.orm import Session

from models.sip_user import PjsipAor, PjsipAuth, PjsipEndpoint
from services.pjsip_disk_sync import _format_callerid


DEFAULT_TEST_USERS: tuple[dict[str, str | int], ...] = (
    {
        "username": "101",
        "password": "strongpassword",
        "callerid": "Test Operator 101",
        "context": "from-internal",
    },
    {
        "username": "102",
        "password": "testpass102",
        "callerid": "Test Operator 102",
        "context": "from-internal",
    },
)


def seed_default_pjsip_users(
    cdr_db: Session,
    instance_name: str,
    transport_type: str,
) -> list[str]:
    """Создаёт пару тестовых endpoint'ов в ps_*; пропускает уже существующие."""
    created: list[str] = []
    transport = f"transport-{transport_type}"

    for user in DEFAULT_TEST_USERS:
        username = str(user["username"])
        existing = (
            cdr_db.query(PjsipEndpoint)
            .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)
            .filter(PjsipAor.reg_server == instance_name)
            .filter(PjsipEndpoint.id == username)
            .first()
        )
        if existing:
            continue

        new_aor = PjsipAor(
            id=username,
            max_contacts=1,
            reg_server=instance_name,
        )
        new_auth = PjsipAuth(
            id=f"{username}-auth",
            username=username,
            password=str(user["password"]),
        )
        cdr_db.add(new_aor)
        cdr_db.add(new_auth)
        cdr_db.flush()

        cdr_db.add(
            PjsipEndpoint(
                id=username,
                aors=username,
                auth=f"{username}-auth",
                auths_id=new_auth.pk,
                aors_id=new_aor.pk,
                context=str(user["context"]),
                transport=transport,
                callerid=_format_callerid(str(user["callerid"]), username),
                mailboxes=f"{username}@default",
            )
        )
        created.append(username)

    if created:
        cdr_db.commit()
    return created

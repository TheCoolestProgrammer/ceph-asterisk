from datetime import datetime
import os
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


from app.core.database import get_db, get_cdr_db
from app.models.asterisk_instance import AsteriskInstance
from sqlalchemy import text

from app.services.asterisk_reload import (
    AsteriskReloadError,
    reload_asterisk_config,
    run_asterisk_cli,
)
from app.services.pjsip_schema import ensure_pjsip_schema
from app.services.voicemail_modules import ensure_voicemail_modules
from app.utils.dialplan_repair import repair_internal_dialplan, repair_queue_and_moh
from app.services.voicemail_sounds import (
    check_voicemail_prompts,
    warn_if_sounds_mount_overrides_defaults,
)
from app.services.instance_container import (
    recreate_asterisk_container,
    verify_instance_config_mount,
    verify_instance_network,
)
from app.utils.instance_paths import docker_volume_config_dir, writable_config_dir
from app.utils.pjsip_views import (
    ps_aors_view_name,
    ps_auths_view_name,
    ps_endpoints_view_name,
    sync_pjsip_views_for_instance,
)

router = APIRouter(prefix="/instances")


@router.post("/{instance_id}/reload")
async def reload_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Перезагрузка конфигурации Asterisk"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        ensure_voicemail_modules(instance)
        schema_added = ensure_pjsip_schema(db_cdr)
        sync_pjsip_views_for_instance(db, db_cdr, instance)
        dialplan_fixed = repair_internal_dialplan(db_cdr, instance_id)
        media_fixed = repair_queue_and_moh(db_cdr, instance_id)
        from app.utils.asterisk_sounds import ensure_astsoundsdir_on_disk

        sounds_conf_fixed = ensure_astsoundsdir_on_disk(instance)
        reload_asterisk_config(instance.name)
        msg = "Configuration reloaded successfully (core + manager)"
        if sounds_conf_fixed:
            msg += "; astsoundsdir => /opt/asterisk-core-sounds in asterisk.conf"
        if dialplan_fixed:
            msg += "; internal dialplan repaired (Echo -> Dial)"
        if media_fixed:
            msg += "; queue/MOH dialplan repaired"
        if schema_added:
            msg += f"; schema columns added: {', '.join(schema_added)}"
        sounds_warn = warn_if_sounds_mount_overrides_defaults(instance)
        if sounds_warn:
            msg += f"; WARNING: {sounds_warn}"
        vm_sounds_warn = check_voicemail_prompts(instance.name)
        if vm_sounds_warn:
            msg += f"; WARNING: {vm_sounds_warn}"
        return {"message": msg}
    except AsteriskReloadError as e:
        detail = e.message
        if e.stderr:
            detail = f"{detail}: {e.stderr}"
        raise HTTPException(status_code=500, detail=detail)


@router.post("/{instance_id}/seed-test-dialplan")
async def seed_test_dialplan(
    instance_id: int,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Тестовый диалплан: from-internal / from-external (777, _XXX, *97, 8000)
    и очередь test-support в queues.conf.
    """
    from app.services.instance_default_configs import seed_test_dialplan as apply_test_dialplan

    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    transport_type = "udp"
    row_counts = apply_test_dialplan(db_cdr, instance_id, transport_type)
    dialplan_fixed = repair_internal_dialplan(db_cdr, instance_id)
    media_fixed = repair_queue_and_moh(db_cdr, instance_id)
    try:
        reload_asterisk_config(instance.name)
    except AsteriskReloadError as e:
        raise HTTPException(status_code=500, detail=e.message) from e

    msg = "Тестовый диалплан записан в ast_config"
    if dialplan_fixed:
        msg += "; internal dialplan repaired"
    if media_fixed:
        msg += "; queue/MOH repaired"

    return {
        "row_counts": row_counts,
        "contexts": ["from-internal", "from-external"],
        "message": msg,
    }


@router.post("/{instance_id}/seed-test-users")
async def seed_test_users(
    instance_id: int,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Добавляет тестовых абонентов 101/102 (если ещё нет) и обновляет pjsip_users.conf."""
    from app.services.instance_pjsip_seed import (
        seed_default_pjsip_users,
        get_test_pjsip_users,
    )
    from app.services.pjsip_disk_sync import write_pjsip_users_conf
    from app.services.voicemail_config import (
        seed_test_voicemail_boxes,
        get_test_voicemail_boxes,
    )

    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    created = seed_default_pjsip_users(
        db_cdr, instance.name, "udp", test_users=get_test_pjsip_users()
    )
    vm_created = seed_test_voicemail_boxes(
        db_cdr,
        instance_id,
        instance.name,
        instance=instance,
        test_boxes=get_test_voicemail_boxes(),
    )
    sync_pjsip_views_for_instance(db, db_cdr, instance)
    write_pjsip_users_conf(instance, db_cdr)
    try:
        reload_asterisk_config(instance.name)
    except AsteriskReloadError as e:
        raise HTTPException(status_code=500, detail=e.message) from e

    return {
        "created": created,
        "voicemail_created": vm_created,
        "message": "Перезагрузите софтфоны: 101/strongpassword, 102/testpass102. "
        "Голосовая почта: *97 или 8097 (Blink), PIN 4242.",
    }


@router.post("/{instance_id}/rebuild-asterisk-image")
async def rebuild_asterisk_image(
    instance_id: int,
    db: Session = Depends(get_db),
):
    """Пересобирает образ my-asterisk с промптами voicemail (vm-intro ulaw)."""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    try:
        import docker

        from app.utils.asterisk_image import (
            ensure_asterisk_image,
            image_has_voicemail_sounds,
        )

        ensure_asterisk_image(docker.from_env(), force_rebuild=True)
        has_sounds = image_has_voicemail_sounds()
        from app.core.config import config

        return {
            "message": "Asterisk image rebuilt",
            "image_tag": config.ASTERISK_IMAGE_TAG,
            "vm_intro_present": has_sounds,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{instance_id}/recreate-container")
async def recreate_container(
    instance_id: int,
    rebuild_image: bool = False,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Пересоздаёт контейнер Asterisk с корректным bind-mount каталога конфигов.
    Нужно, если /etc/asterisk в контейнере не совпадает с файлами на хосте.
    """
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        from app.services.voicemail_modules import ensure_voicemail_modules
        from app.utils.instance_voicemail_spool import warn_if_empty_sounds_dir
        from app.services.voicemail_sounds import warn_if_sounds_mount_overrides_defaults
        from app.utils.asterisk_sounds import ensure_astsoundsdir_on_disk

        sync_pjsip_views_for_instance(db, db_cdr, instance)
        ensure_voicemail_modules(instance)
        if ensure_astsoundsdir_on_disk(instance):
            msg_extra = "astsoundsdir обновлён в asterisk.conf; "
        else:
            msg_extra = ""
        volume_path = recreate_asterisk_container(
            instance, db, force_rebuild_image=rebuild_image
        )
        reload_asterisk_config(instance.name)
        mount = verify_instance_config_mount(instance)
        msg = f"{msg_extra}Container recreated"
        if rebuild_image:
            msg += " (Asterisk image rebuilt with voicemail sounds)"
        for warn in (
            warn_if_empty_sounds_dir(instance),
            warn_if_sounds_mount_overrides_defaults(instance),
        ):
            if warn:
                msg += f"; WARNING: {warn}"
        return {
            "message": msg,
            "config_volume_host_path": volume_path,
            "mount": mount,
        }
    except Exception as e:
        instance.status = "error"
        db.commit()
        raise HTTPException(
            status_code=500, detail=f"Failed to recreate container: {e}"
        ) from e


@router.get("/{instance_id}/pjsip-diagnose")
async def pjsip_diagnose(
    instance_id: int,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Проверка PJSIP realtime: VIEW, строки в БД, вывод `pjsip show endpoints`."""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    schema_added = ensure_pjsip_schema(db_cdr)
    sync_pjsip_views_for_instance(db, db_cdr, instance)

    ep_view = ps_endpoints_view_name(instance_id)
    aor_view = ps_aors_view_name(instance_id)
    auth_view = ps_auths_view_name(instance_id)

    def _count(view: str) -> int:
        return db_cdr.execute(text(f"SELECT COUNT(*) FROM {view}")).scalar() or 0

    endpoints_db = (
        db_cdr.execute(
            text(
                f"""
                SELECT e.id, e.aors, e.auth, e.context, e.transport,
                       au.username, au.password
                FROM {ep_view} e
                JOIN {auth_view} au ON e.auth = au.id
                """
            )
        )
        .mappings()
        .all()
    )

    cli: dict[str, str] = {}
    cli_errors: dict[str, str] = {}
    cli_commands = [
        "odbc show",
        "pjsip show registrations",
        "pjsip show endpoints",
        "dialplan show from-internal",
    ]
    for ep in endpoints_db:
        cli_commands.append(f"pjsip show endpoint {ep['id']}")
        cli_commands.append(f"pjsip show aor {ep['aors']}")
    for cmd in cli_commands:
        try:
            result = run_asterisk_cli(instance.name, cmd, strict=False)
            cli[cmd] = (result.stdout or result.stderr or "").strip()
        except AsteriskReloadError as e:
            cli_errors[cmd] = e.message

    pjsip_users_path = ""
    pjsip_users_preview = ""
    config_dir = writable_config_dir(instance)
    if not config_dir.startswith("ceph://"):
        pjsip_users_path = os.path.join(config_dir, "pjsip_users.conf")
        if os.path.isfile(pjsip_users_path):
            with open(pjsip_users_path, encoding="utf-8") as f:
                pjsip_users_preview = f.read()[:2000]

    mount = verify_instance_config_mount(instance)
    network = verify_instance_network(instance)

    registrations_out = cli.get("pjsip show registrations", "")
    endpoints_out = cli.get("pjsip show endpoints", "")
    has_active_registration = (
        "Registered" in registrations_out
        or "Avail" in endpoints_out
        or "Not in use" in endpoints_out
    )

    sip_accounts = [
        {
            "extension": row["id"],
            "sip_username": row["username"],
            "password": row["password"],
            "aor": row["aors"],
            "registered": row["aors"] in registrations_out
            and row["id"] in endpoints_out,
        }
        for row in endpoints_db
    ]

    return {
        "instance": instance.name,
        "writable_config_dir": config_dir,
        "docker_volume_config_dir": docker_volume_config_dir(instance),
        "config_mount": mount,
        "network": network,
        "db_config_path": instance.config_path,
        "pjsip_users_conf_path": pjsip_users_path,
        "pjsip_users_conf_preview": pjsip_users_preview,
        "reg_server_filter": instance.name,
        "views": {
            "endpoints": ep_view,
            "aors": aor_view,
            "auths": auth_view,
            "contacts_table": "ps_contacts (base, not VIEW)",
        },
        "counts": {
            "endpoints_in_view": _count(ep_view),
            "aors_in_view": _count(aor_view),
            "auths_in_view": _count(auth_view),
        },
        "endpoints_in_db": [
            {k: v for k, v in dict(row).items() if k != "password"}
            for row in endpoints_db
        ],
        "sip_accounts": sip_accounts,
        "sip_server": {
            "host": "<IP_сервера_debian>",
            "port": instance.sip_port,
            "transport": "UDP",
            "context": "from-internal",
        },
        "registration_ok": has_active_registration,
        "schema_columns_added": schema_added,
        "asterisk_cli": cli,
        "asterisk_cli_errors": cli_errors,
        "hints": [
            "pjsip show registrations пусто + Unavailable = Contact не сохранён; нужен contact=memory в sorcery.conf + reload",
            "не звоните с 101 на 101 — нужны два софтфона (101 и 102)",
            "«Удалённая сторона не найдена» = у callee нет Contact (не зарегистрирован)",
            "POST /instances/{id}/seed-test-dialplan — тестовый from-internal/from-external",
            "POST /instances/{id}/seed-test-users — добавить 101 и 102, затем reload",
            "8000 без звука: нужны RTP-порты (network.rtp_reachable) и res_musiconhold.so",
            f"RTP UDP {instance.rtp_port_start}-{instance.rtp_port_end} должны быть проброшены в docker",
            "dialplan: _XXX => Dial(PJSIP/${EXTEN}) в from-internal",
        ],
    }


@router.post("{instance_id}/simulate-call")
async def simulate_single_call(
    instance_id: int,
    src: str = "6001",
    dst: str = "6002",
    db: Session = Depends(get_db),
):
    """Симуляция одного тестового звонка"""

    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Используем Asterisk Manager Interface для инициации звонка
        # Или создаем CDR запись напрямую
        call_date = datetime.now()

        query = """
        INSERT INTO cdr 
        (calldate, clid, src, dst, dcontext, channel, dstchannel, lastapp, lastdata, 
         duration, billsec, disposition, amaflags, accountcode, uniqueid, userfield, instance_name)
        VALUES 
        (:calldate, :clid, :src, :dst, :dcontext, :channel, :dstchannel, :lastapp, :lastdata,
         :duration, :billsec, :disposition, :amaflags, :accountcode, :uniqueid, :userfield, :instance_name)
        """

        params = {
            "calldate": call_date,
            "clid": f'"{src}" <{src}>',
            "src": src,
            "dst": dst,
            "dcontext": "local",
            "channel": f"SIP/{src}-00000001",
            "dstchannel": f"SIP/{dst}-00000002",
            "lastapp": "Dial",
            "lastdata": f"SIP/{dst},20",
            "duration": 30,
            "billsec": 25,
            "disposition": "ANSWERED",
            "amaflags": 0,
            "accountcode": "",
            "uniqueid": f"{int(call_date.timestamp())}.{random.randint(1000, 9999)}",
            "userfield": "manual_simulation",
            "instance_name": instance.name,
        }

        db.execute(text(query), params)
        db.commit()

        return {"message": f"Call simulated from {src} to {dst}", "call_data": params}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to simulate call: {str(e)}"
        )

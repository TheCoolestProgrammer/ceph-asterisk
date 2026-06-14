import asyncio

import os
import shutil
import subprocess
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import yaml
from app.core.config import config

from app.core.database import SessionLocal, get_cdr_db, get_db
from app.models.asterisk_instance import AsteriskInstance
from app.utils.ast_config_ini import seed_config_from_ini
from app.utils.ast_config_views import (
    build_extconfig_conf,
    create_ast_config_view,
    delete_ast_config_for_instance,
    drop_ast_config_view,
)
from app.utils.pjsip_views import (
    create_pjsip_views,
    drop_pjsip_views,
    sync_pjsip_views_for_instance,
)
from app.services.ast_config_history import (
    apply_http_port_change,
    apply_manager_ami_port_change,
    apply_rtp_ports_change,
)
from app.services.instance_default_configs import (
    get_db_config_templates,
    get_disk_config_templates,
)
from app.services.instance_pjsip_seed import seed_default_pjsip_users, get_test_pjsip_users
from app.services.pjsip_schema import ensure_pjsip_schema
from app.services.filebeat_config import write_filebeat_config
from app.services.instance_container import run_asterisk_container
from app.services.instance_runtime import apply_instance_ports_runtime
from app.utils.instance_paths import (
    docker_volume_config_dir,
    writable_config_dir,
    writable_config_dir_for_name,
)

# from app.models.sip_user import SIPUser
from app.schemas.asterisk import (
    AsteriskInstanceCreate,
    AsteriskInstanceResponse,
    AsteriskInstanceUpdate,
    ChangeCDRStatus,
    CDRState,
)
from sqlalchemy.orm import Session
from panoramisk import Manager, Message

router = APIRouter(prefix="/instances")


async def unload_module(
    modlue: str, instance_name: str, db: SessionLocal = Depends(get_db)
):
    instance = (
        db.query(AsteriskInstance)
        .filter(AsteriskInstance.name == instance_name)
        .first()
    )
    if instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance '{instance_name}' not found"
        )

    manager = Manager(
        host="asterisk-" + instance.name,
        port=instance.ami_port,
        username=config.MYSQL_ASTERISK_USER,
        secret=config.MYSQL_ASTERISK_USER_PASSWORD,
        ssl=False,
        encoding="utf8",
    )
    try:
        await manager.connect()

        # Передаем словарь явно. Action — ключ, Command — доп. поле.
        # action = {'Action': 'ModuleUnload', 'Module': modlue}
        action = {"Action": "ListCommands"}
        response = await asyncio.wait_for(manager.send_action(action), timeout=5.0)
        for line in response.iter_lines():
            print(response.content)

        manager.close()
        return response
    except Exception as e:
        if manager:
            manager.close()
        raise HTTPException(status_code=500, detail=f"AMI Error: {str(e)}")


async def send_ami_command(
    command: str, instance_name: str, db: SessionLocal = Depends(get_db)
):
    instance = (
        db.query(AsteriskInstance)
        .filter(AsteriskInstance.name == instance_name)
        .first()
    )
    if instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance '{instance_name}' not found"
        )

    manager = Manager(
        host="asterisk-" + instance.name,
        port=instance.ami_port,
        username=config.MYSQL_ASTERISK_USER,
        secret=config.MYSQL_ASTERISK_USER_PASSWORD,
        ssl=False,
        encoding="utf8",
    )
    try:
        await manager.connect()

        # Передаем словарь явно. Action — ключ, Command — доп. поле.
        action = {"Action": "Command", "Command": command}

        response = await asyncio.wait_for(manager.send_action(action), timeout=5.0)
        for line in response.iter_lines():
            print(response.content)

        manager.close()
        return response
    except Exception as e:
        if manager:
            manager.close()
        raise HTTPException(status_code=500, detail=f"AMI Error: {str(e)}")


@router.post("/cdr_change_status")
async def set_cdr_status(status: ChangeCDRStatus, db: SessionLocal = Depends(get_db)):
    # Включаем или выключаем запись CDR на лету
    # Команда 'cdr set debug off/on' — самый быстрый способ
    action = CDRState.ON if status.enabled else CDRState.OFF

    # Мы можем либо менять статус через debug,
    # либо через полноценный reload модуля (если вы правили конфиг программно)

    # cmd = f"cdr set core channeldefaultenabled {action}"
    # cmd = "cdr show status"
    # cmd = "module unload cdr_adaptive_odbc.so"
    cmd = "config reload"
    # Если вы всё же хотите править конфиг и делать reload:
    # 1. Сначала ваш код правит файл cdr.conf
    # 2. Потом cmd = "cdr reload"

    response = await send_ami_command(cmd, status.instance_name, db)
    # response = await unload_module("cdr_adaptive_odbc.so",status.instance_name,db)
    return {
        "status": "success",
        "cdr_enabled": status.enabled,
        "asterisk_response": response,
    }


@router.post("/send_comand/{instance_name}")
async def send_comand_route(
    comand: str, instance_name: str, db: SessionLocal = Depends(get_db)
):

    response = await send_ami_command(comand, instance_name, db)
    # response = await unload_module("cdr_adaptive_odbc.so",status.instance_name,db)
    return response


@router.get("/", response_model=list[AsteriskInstanceResponse])
def list_instances(db: SessionLocal = Depends(get_db)):
    return db.query(AsteriskInstance).all()


@router.get("/{instance_id}", response_model=AsteriskInstanceResponse)
async def get_instance(instance_id: int, db: Session = Depends(get_db)):
    """Получение информации о конкретном экземпляре"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


@router.post("/", response_model=AsteriskInstanceResponse)
async def create_instance(
    instance: AsteriskInstanceCreate,
    create_test_users: bool,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Создание нового экземпляра Asterisk"""
    # Check if instance name already exists
    if (
        db.query(AsteriskInstance)
        .filter(AsteriskInstance.name == instance.name)
        .first()
    ):
        raise HTTPException(status_code=400, detail="Instance name already exists")

    # Check port conflicts
    if (
        db.query(AsteriskInstance)
        .filter(
            (AsteriskInstance.sip_port == instance.sip_port)
            | (AsteriskInstance.http_port == instance.http_port)
            | (AsteriskInstance.rtp_port_start == instance.rtp_port_start)
            | (AsteriskInstance.rtp_port_end == instance.rtp_port_end)
            | (AsteriskInstance.ami_port == instance.ami_port)
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Ports already in use")

    # Create config directory
    config_dir = writable_config_dir_for_name(instance.name)
    os.chmod(config_dir, 0o777)

    os.makedirs(f"{config_dir}/drivers", exist_ok=True)
    os.chmod(f"{config_dir}/drivers", 0o777)

    os.makedirs(f"{config_dir}/asterisk_logs", exist_ok=True)
    os.chmod(f"{config_dir}/asterisk_logs", 0o777)

    db_instance = None
    try:
        transport_type = instance.transport_type.value
        db_instance = AsteriskInstance(
            name=instance.name,
            sip_port=instance.sip_port,
            http_port=instance.http_port,
            rtp_port_start=instance.rtp_port_start,
            rtp_port_end=instance.rtp_port_end,
            ami_port=instance.ami_port,
            config_path=config_dir,
            status="creating",
        )
        db.add(db_instance)
        db.commit()
        db.refresh(db_instance)

        try:
            create_default_configs(
                config_dir,
                instance,
                transport_type,
                db_cdr,
                db_instance.id,
            )
            ensure_pjsip_schema(db_cdr)
            create_ast_config_view(db_cdr, db_instance.id)
            create_pjsip_views(db_cdr, db_instance.id, db_instance.name)
        except Exception:
            delete_ast_config_for_instance(db_cdr, db_instance.id)
            drop_ast_config_view(db_cdr, db_instance.id)
            drop_pjsip_views(db_cdr, db_instance.id)
            db.delete(db_instance)
            db.commit()
            raise

        if create_test_users:
            seed_default_pjsip_users(
                db_cdr,
                db_instance.name,
                transport_type,
                test_users=get_test_pjsip_users(),
            )
            from app.services.pjsip_disk_sync import write_pjsip_users_conf
            from app.services.voicemail_config import (
                seed_test_voicemail_boxes,
                get_test_voicemail_boxes,
            )
            seed_test_voicemail_boxes(
                db_cdr,
                db_instance.id,
                db_instance.name,
                instance=db_instance,
                test_boxes=get_test_voicemail_boxes(),
            )
            write_pjsip_users_conf(db_instance, db_cdr)

        background_tasks.add_task(_start_asterisk_container_task, db_instance.id)

        return db_instance

    except Exception as e:
        # Cleanup on error
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)
        raise HTTPException(
            status_code=500, detail=f"Failed to create instance: {str(e)}"
        )


@router.put("/{instance_id}", response_model=AsteriskInstanceResponse)
async def update_instance(
    instance_id: int,
    instance_update: AsteriskInstanceUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Обновление экземпляра Asterisk"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    if instance_update.name and instance_update.name != instance.name:
        existing_instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.name == instance_update.name)
            .first()
        )
        if existing_instance:
            raise HTTPException(status_code=400, detail="Instance name already exists")

    update_data = instance_update.model_dump(exclude_unset=True)
    change_author = update_data.pop("change_author", None)
    update_data.pop("ami_port", None)
    update_data.pop("http_port", None)
    update_data.pop("rtp_port_start", None)
    update_data.pop("rtp_port_end", None)
    ports_runtime_needed = False
    author = change_author or "api"

    new_http_port = (
        instance_update.http_port
        if "http_port" in instance_update.model_fields_set
        else None
    )
    new_ami_port = (
        instance_update.ami_port
        if "ami_port" in instance_update.model_fields_set
        else None
    )
    new_rtp_start = (
        instance_update.rtp_port_start
        if "rtp_port_start" in instance_update.model_fields_set
        else None
    )
    new_rtp_end = (
        instance_update.rtp_port_end
        if "rtp_port_end" in instance_update.model_fields_set
        else None
    )

    if new_http_port is not None and new_http_port != instance.http_port:
        existing_http_port = (
            db.query(AsteriskInstance)
            .filter(
                AsteriskInstance.http_port == new_http_port,
                AsteriskInstance.id != instance_id,
            )
            .first()
        )
        if existing_http_port:
            raise HTTPException(status_code=400, detail="HTTP port already in use")

        try:
            apply_http_port_change(
                db_cdr,
                instance_id=instance_id,
                old_http_port=instance.http_port,
                new_http_port=new_http_port,
                author=author,
            )
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        instance.http_port = new_http_port
        ports_runtime_needed = True

    if new_ami_port is not None and new_ami_port != instance.ami_port:
        existing_ami_port = (
            db.query(AsteriskInstance)
            .filter(
                AsteriskInstance.ami_port == new_ami_port,
                AsteriskInstance.id != instance_id,
            )
            .first()
        )
        if existing_ami_port:
            raise HTTPException(status_code=400, detail="AMI port already in use")

        try:
            apply_manager_ami_port_change(
                db_cdr,
                instance_id=instance_id,
                old_ami_port=instance.ami_port,
                new_ami_port=new_ami_port,
                author=author,
            )
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        instance.ami_port = new_ami_port
        ports_runtime_needed = True

    effective_rtp_start = (
        new_rtp_start if new_rtp_start is not None else instance.rtp_port_start
    )
    effective_rtp_end = (
        new_rtp_end if new_rtp_end is not None else instance.rtp_port_end
    )

    if new_rtp_start is not None or new_rtp_end is not None:
        if effective_rtp_start >= effective_rtp_end:
            raise HTTPException(
                status_code=400,
                detail="rtp_port_start must be less than rtp_port_end",
            )

        if (
            effective_rtp_start != instance.rtp_port_start
            or effective_rtp_end != instance.rtp_port_end
        ):
            if new_rtp_start is not None and new_rtp_start != instance.rtp_port_start:
                conflict = (
                    db.query(AsteriskInstance)
                    .filter(
                        AsteriskInstance.rtp_port_start == new_rtp_start,
                        AsteriskInstance.id != instance_id,
                    )
                    .first()
                )
                if conflict:
                    raise HTTPException(
                        status_code=400, detail="RTP start port already in use"
                    )
            if new_rtp_end is not None and new_rtp_end != instance.rtp_port_end:
                conflict = (
                    db.query(AsteriskInstance)
                    .filter(
                        AsteriskInstance.rtp_port_end == new_rtp_end,
                        AsteriskInstance.id != instance_id,
                    )
                    .first()
                )
                if conflict:
                    raise HTTPException(
                        status_code=400, detail="RTP end port already in use"
                    )

            try:
                apply_rtp_ports_change(
                    db_cdr,
                    instance_id=instance_id,
                    old_rtp_start=instance.rtp_port_start,
                    old_rtp_end=instance.rtp_port_end,
                    new_rtp_start=effective_rtp_start,
                    new_rtp_end=effective_rtp_end,
                    author=author,
                )
            except ValueError as e:
                raise HTTPException(status_code=500, detail=str(e))

            instance.rtp_port_start = effective_rtp_start
            instance.rtp_port_end = effective_rtp_end
            ports_runtime_needed = True

    for field, value in update_data.items():
        setattr(instance, field, value)

    db.commit()
    db.refresh(instance)

    if ports_runtime_needed:
        background_tasks.add_task(apply_instance_ports_runtime, instance_id)

    return instance


@router.delete("/{instance_id}")
def delete_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Stop and remove container
        from app.services.instance_compose import compose_cli, compose_workdir

        compose_path = compose_workdir()
        filename = f"docker-compose-{instance.name}.yml"
        # Проверяем существование директории docker-compose перед удалением
        if os.path.exists(compose_path):
            result = subprocess.run(
                compose_cli(instance.name, "down", "-v"),
                cwd=compose_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"Warning: Failed to stop container: {result.stderr}")
        else:
            print(f"Compose path not found: {compose_path}")

        # Cleanup config directory with error handling
        if instance.config_path:
            config_path = instance.config_path
            # Если config_path начинается с ceph://, пропускаем удаление файлов
            if config_path.startswith("ceph://"):
                print(f"Skipping filesystem cleanup for Ceph path: {config_path}")
            elif os.path.exists(config_path):
                try:
                    shutil.rmtree(config_path)
                    print(f"Config directory removed: {config_path}")
                except FileNotFoundError:
                    print(f"Config directory already deleted: {config_path}")
                except Exception as e:
                    print(
                        f"Warning: Could not remove config directory {config_path}: {e}"
                    )
            else:
                print(f"Config directory not found: {config_path}")

        # Cleanup compose directory with error handling
        if os.path.exists(compose_path):
            try:
                os.remove(f"{compose_path}/{filename}")
                # shutil.rmtree(compose_path)
                print(f"Compose file removed: {filename}")
            except FileNotFoundError:
                print(f"Compose file already deleted: {filename}")
            except Exception as e:
                print(f"Warning: Could not remove compose file {filename}: {e}")
        else:
            print(f"Compose file not found: {filename}")

        delete_ast_config_for_instance(db_cdr, instance_id)
        drop_ast_config_view(db_cdr, instance_id)
        drop_pjsip_views(db_cdr, instance_id)

        db.delete(instance)
        db.commit()

        return {"message": "Instance deleted successfully"}

    except subprocess.TimeoutExpired:
        db.rollback()
        db_cdr.rollback()
        raise HTTPException(status_code=500, detail="Timeout during container shutdown")
    except Exception as e:
        db.rollback()
        db_cdr.rollback()
        print(f"Error during instance deletion: {e}")
        raise HTTPException(status_code=500, detail=f"Error during deletion: {str(e)}")


def create_default_configs(
    config_dir: str,
    instance: AsteriskInstanceCreate,
    transport_type: str,
    db_cdr: Session,
    instance_id: int,
):
    """Сидирует конфиги в ast_config и пишет на диск только bootstrap-файлы."""

    for filename, content in get_db_config_templates(instance, transport_type).items():
        seed_config_from_ini(db_cdr, instance_id, filename, content)
    db_cdr.commit()

    disk_configs = get_disk_config_templates(instance, transport_type)
    disk_configs["extconfig.conf"] = build_extconfig_conf(instance_id)

    for filename, content in disk_configs.items():
        filepath = os.path.join(config_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        # Устанавливаем правильные права
        os.chmod(filepath, 0o777)
        os.chown(filepath, config.ASTERISK_UID, config.ASTERISK_GID)
        # try:
        #     os.chown(filepath, 0, 0)
        # except PermissionError:
        #     # Если нет прав на смену владельца, используем sudo
        #     subprocess.run(['sudo', 'chown', f'{0}:{0}', filepath])
    # os.chmod(config_dir, 0o777)
    print(f"Конфиги созданы в {config_dir}")
    write_filebeat_config(instance.name)


def _start_asterisk_container_task(instance_id: int) -> None:
    db = SessionLocal()
    try:
        instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.id == instance_id)
            .first()
        )
        if instance is None:
            return
        start_asterisk_container(instance, db)
    finally:
        db.close()


def start_asterisk_container_by_library(instance: AsteriskInstance, db: Session):
    try:
        run_asterisk_container(instance, db)
        print(f"Контейнер {instance.name} запущен успешно")
    except Exception as e:
        instance.status = "error"
        db.commit()
        print(f"Ошибка запуска: {e}")
    # compose_path = f"./docker-compose/asterisk-{instance.name}"
    # os.makedirs(compose_path, exist_ok=True)

    # with open(f"{compose_path}/docker-compose.yml", "w") as f:
    #     yaml.dump(compose_config, f)

    # Перед запуском проверяем что файлы созданы

    # ????????

    # print(f"Проверка конфигов в {instance.config_path}:")
    # for file in os.listdir(instance.config_path):
    #     filepath = os.path.join(instance.config_path, file)
    #     if os.path.isfile(filepath):
    #         print(f"  {file} - {os.path.getsize(filepath)} bytes")

    # Запускаем контейнер
    # result = subprocess.run(
    #     ["docker-compose", "up", "-d"],
    #     cwd=compose_path,
    #     capture_output=True,
    #     text=True,
    #     timeout=30,
    # )

    # if result.returncode == 0:
    #     instance.status = "running"
    #     db.commit()
    #     print(f"Контейнер {instance.name} запущен успешно")
    # else:
    #     instance.status = "error"
    #     db.commit()
    #     print(f"Ошибка запуска: {result.stderr}")

    # except Exception as e:
    #     print(f"Error in start_asterisk_container: {e}")
    #     instance.status = "error"
    #     db.commit()


def start_asterisk_container(instance: AsteriskInstance, db: Session):
    """Запуск asterisk + filebeat с volume {HOST_PROJECT_PATH}/asterisk_configs/{name}."""
    from app.services.instance_compose import stop_instance_stack

    config_dir = docker_volume_config_dir(instance)
    print(f"Проверка конфигов в {config_dir}:")
    if os.path.isdir(config_dir):
        for file in os.listdir(config_dir):
            filepath = os.path.join(config_dir, file)
            if os.path.isfile(filepath):
                print(f"  {file} - {os.path.getsize(filepath)} bytes")

    try:
        stop_instance_stack(instance)
        run_asterisk_container(instance, db)
        print(f"Контейнер {instance.name} запущен, volume {config_dir}:/etc/asterisk")
    except Exception as e:
        instance.status = "error"
        db.commit()
        print(f"Ошибка запуска: {e}")

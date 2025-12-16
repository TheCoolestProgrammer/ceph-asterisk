import os
import shutil
import subprocess
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import yaml

from database import SessionLocal, get_db
from models.asterisk_instance import AsteriskInstance
from models.sip_user import SIPUser
from schemas.asterisk import (
    AsteriskInstanceCreate,
    AsteriskInstanceResponse,
    AsteriskInstanceUpdate,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/instances")


@router.get("", response_model=list[AsteriskInstanceResponse])
def list_instances(db: SessionLocal = Depends(get_db)):
    return db.query(AsteriskInstance).all()


@router.get("{instance_id}", response_model=AsteriskInstanceResponse)
async def get_instance(instance_id: int, db: Session = Depends(get_db)):
    """Получение информации о конкретном экземпляре"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


@router.post("", response_model=AsteriskInstanceResponse)
async def create_instance(
    instance: AsteriskInstanceCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    create_test_users: bool = True,
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
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Ports already in use")

    # Create config directory
    config_dir = f"./asterisk_configs/{instance.name}"
    os.makedirs(config_dir, exist_ok=True)

    try:
        # Create basic Asterisk config files
        create_default_configs(config_dir, instance)

        # Save to database
        db_instance = AsteriskInstance(
            name=instance.name,
            sip_port=instance.sip_port,
            http_port=instance.http_port,
            config_path=config_dir,
            status="creating",
        )
        db.add(db_instance)
        db.commit()
        db.refresh(db_instance)

        # Start container in background
        background_tasks.add_task(start_asterisk_container, db_instance, db)
        if create_test_users:
            test_users = [
                {
                    "username": "1001",
                    "password": "test1001",
                    "caller_id": "Test User 1",
                    "account_code": "test",
                    "context": "internal",
                },
                {
                    "username": "1002",
                    "password": "test1002",
                    "caller_id": "Test User 2",
                    "account_code": "test",
                    "context": "internal",
                },
            ]

            for user_data in test_users:
                db_user = SIPUser(**user_data, instance_name=db_instance.name)
                db.add(db_user)

            db.commit()

        return db_instance

    except Exception as e:
        # Cleanup on error
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)
        raise HTTPException(
            status_code=500, detail=f"Failed to create instance: {str(e)}"
        )


@router.put("{instance_id}", response_model=AsteriskInstanceResponse)
async def update_instance(
    instance_id: int,
    instance_update: AsteriskInstanceUpdate,
    db: Session = Depends(get_db),
):
    """Обновление экземпляра Asterisk"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Проверяем уникальность имени, если оно меняется
    if instance_update.name and instance_update.name != instance.name:
        existing_instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.name == instance_update.name)
            .first()
        )
        if existing_instance:
            raise HTTPException(status_code=400, detail="Instance name already exists")

    # Проверяем уникальность портов, если они меняются
    if instance_update.sip_port and instance_update.sip_port != instance.sip_port:
        existing_sip_port = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.sip_port == instance_update.sip_port)
            .first()
        )
        if existing_sip_port:
            raise HTTPException(status_code=400, detail="SIP port already in use")

    if instance_update.http_port and instance_update.http_port != instance.http_port:
        existing_http_port = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.http_port == instance_update.http_port)
            .first()
        )
        if existing_http_port:
            raise HTTPException(status_code=400, detail="HTTP port already in use")

    # Обновляем поля
    update_data = instance_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(instance, field, value)

    db.commit()
    db.refresh(instance)

    return instance


@router.delete("{instance_id}")
def delete_instance(instance_id: int, db: Session = Depends(get_db)):
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Stop and remove container
        compose_path = f"./docker-compose/asterisk-{instance.name}"

        # Проверяем существование директории docker-compose перед удалением
        if os.path.exists(compose_path):
            result = subprocess.run(
                ["docker-compose", "down"],
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
                shutil.rmtree(compose_path)
                print(f"Compose directory removed: {compose_path}")
            except FileNotFoundError:
                print(f"Compose directory already deleted: {compose_path}")
            except Exception as e:
                print(
                    f"Warning: Could not remove compose directory {compose_path}: {e}"
                )
        else:
            print(f"Compose directory not found: {compose_path}")

        # Delete from database
        db.delete(instance)
        db.commit()

        return {"message": "Instance deleted successfully"}

    except subprocess.TimeoutExpired:
        db.rollback()
        raise HTTPException(status_code=500, detail="Timeout during container shutdown")
    except Exception as e:
        db.rollback()
        print(f"Error during instance deletion: {e}")
        raise HTTPException(status_code=500, detail=f"Error during deletion: {str(e)}")


def create_default_configs(config_dir: str, instance: AsteriskInstanceCreate):
    """Создание конфигурационных файлов с правильными правами"""

    # Создаем директорию если не существует
    os.makedirs(config_dir, exist_ok=True)

    configs = {
        "asterisk.conf": f"""[directories]
            astetcdir => /etc/asterisk
            astmoddir => /usr/lib/asterisk/modules
            astvarlibdir => /var/lib/asterisk
            astdbdir => /var/lib/asterisk
            astkeydir => /var/lib/asterisk
            astdatadir => /var/lib/asterisk
            astagidir => /var/lib/asterisk/agi-bin
            astspooldir => /var/spool/asterisk
            astrundir => /var/run/asterisk
            astlogdir => /var/log/asterisk

            [options]
            verbose = 3
            debug = 0
            maxfiles = 100000
            systemname = {instance.name}
            """,
        "logger.conf": """[general]
            dateformat=%F %T

            [logfiles]
            console => error,warning,notice
            messages => notice,warning,error
            """,
        "modules.conf": """[modules]
            autoload = yes
            load = pbx_config.so
            load = app_dial.so
            load = app_playback.so
            load = res_rtp_asterisk.so
            load = codec_ulaw.so
            load = codec_alaw.so
            load = format_wav.so
            load = chan_sip.so
            """,
        "sip.conf": f"""[general]
            context = default
            bindaddr = 0.0.0.0
            bindport = {instance.sip_port}
            srvlookup = yes
            udpbindaddr = 0.0.0.0:{instance.sip_port}
            transport = udp

            [6001]
            type = friend
            host = dynamic
            secret = 123456
            context = local
            dtmfmode = rfc2833

            [6002]
            type = friend
            host = dynamic
            secret = 123456
            context = local
            dtmfmode = rfc2833
            """,
        "extensions.conf": """[general]
            static=yes

            [default]
            exten => 100,1,Answer()
                same => n,Playback(hello-world)
                same => n,Hangup()

            [local]
            exten => 6001,1,Dial(SIP/6001,20)
            exten => 6002,1,Dial(SIP/6002,20)
            exten => _6XXX,1,Dial(SIP/${EXTEN})
            exten => h,1,Hangup()
            """,
        "http.conf": f"""[general]
            enabled=yes
            bindaddr=0.0.0.0
            bindport={instance.http_port}
            """,
        "rtp.conf": """[general]
            rtpstart=10000
            rtpend=20000
            """,
        "stasis.conf": """[general]
            enabled=no
            """,
        "cdr.conf": """[general]
            enable=yes

            ; CDR в CSV файл
            [csv]
            usegmtime=yes
            loguniqueid=yes
            loguserfield=yes

            ; CDR в MySQL (основной способ)
            [mysql]
            dsn=MySQL-asterisk-cdr
            loguniqueid=yes
            loguserfield=yes
            table=cdr

            ; CDR в PostgreSQL (альтернатива)
            ;[pgsql]
            ;dsn=PostgreSQL-asterisk-cdr
            """,
        "cdr_mysql.conf": f"""[global]
            hostname=localhost
            dbname=asterisk_cdr
            password=mysql_password
            user=asterisk_user
            port=3306

            [asterisk_cdr]
            table=cdr
            ;timezone=UTC
            """,
    }

    for filename, content in configs.items():
        filepath = os.path.join(config_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        # Устанавливаем правильные права
        os.chmod(filepath, 0o644)

    print(f"Конфиги созданы в {config_dir}")


def start_asterisk_container(instance: AsteriskInstance, db: Session):
    # Create docker-compose.yml
    compose_config = {
        "version": "3.8",
        "services": {
            f"asterisk-{instance.name}": {
                "image": "andrius/asterisk:latest",
                "container_name": f"asterisk-{instance.name}",
                "ports": [
                    f"{instance.sip_port}:{instance.sip_port}/udp",
                    f"{instance.http_port}:{instance.http_port}/tcp",
                ],
                "volumes": [
                    f"{os.path.abspath(instance.config_path)}:/etc/asterisk:rw"
                ],
                # "restart": "unless-stopped",
                "network_mode": "bridge",
                "privileged": True,
            }
        },
    }

    compose_path = f"./docker-compose/asterisk-{instance.name}"
    os.makedirs(compose_path, exist_ok=True)

    with open(f"{compose_path}/docker-compose.yml", "w") as f:
        yaml.dump(compose_config, f)

    # Перед запуском проверяем что файлы созданы
    print(f"Проверка конфигов в {instance.config_path}:")
    for file in os.listdir(instance.config_path):
        filepath = os.path.join(instance.config_path, file)
        if os.path.isfile(filepath):
            print(f"  {file} - {os.path.getsize(filepath)} bytes")

    # Запускаем контейнер
    result = subprocess.run(
        ["docker-compose", "up", "-d"],
        cwd=compose_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0:
        instance.status = "running"
        db.commit()
        print(f"Контейнер {instance.name} запущен успешно")
    else:
        instance.status = "error"
        db.commit()
        print(f"Ошибка запуска: {result.stderr}")

    # except Exception as e:
    #     print(f"Error in start_asterisk_container: {e}")
    #     instance.status = "error"
    #     db.commit()

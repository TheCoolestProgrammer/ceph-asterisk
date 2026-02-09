import docker
import os
import shutil
import subprocess
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import yaml
from config import config

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
    create_test_users: bool,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
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
            | (AsteriskInstance.rtp_port_start==instance.rtp_port_start)
            | (AsteriskInstance.rtp_port_end==instance.rtp_port_end)
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Ports already in use")

    # Create config directory
    config_dir = f"./asterisk_configs/{instance.name}"
    os.makedirs(config_dir, exist_ok=True)
    os.chmod(config_dir, 0o777)
    os.makedirs(f"{config_dir}/drivers", exist_ok=True)
    os.chmod(f"{config_dir}/drivers", 0o777)
    try:
        # Create basic Asterisk config files
        create_default_configs(config_dir, instance)

        # Save to database
        db_instance = AsteriskInstance(
            name=instance.name,
            sip_port=instance.sip_port,
            http_port=instance.http_port,
            rtp_port_start=instance.rtp_port_start,
            rtp_port_end=instance.rtp_port_end,
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
    # os.makedirs(config_dir, exist_ok=True)

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
load => pbx_config.so
load => app_dial.so
load => app_playback.so
load => res_rtp_asterisk.so
load => codec_ulaw.so
load => codec_alaw.so
load => format_wav.so
load => res_odbc.so
load => cdr_adaptive_odbc.so
            
            """,
        "pjsip.conf": f"""[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:{instance.sip_port}
[101]
type=endpoint
context=from-internal
disallow=all
allow=ulaw,alaw
auth=101-auth
aors=101-aor

[101-auth]
type=auth
auth_type=userpass
password=strongpassword  ; Ваш пароль
username=101

[101-aor]
type=aor
max_contacts=1
default_expiration=3600

[200]
type=endpoint
context=from-external ; Важно! У внешних звонков должен быть свой контекст
disallow=all
allow=ulaw,alaw
auth=200-auth
aors=200-aor
direct_media=no

[200-auth]
type=auth
auth_type=userpass
password=customerpass
username=200

[200-aor]
type=aor
max_contacts=1

            """,
        "extensions.conf": """[from-internal]
exten => 600,1,Answer()

same => n,Echo()
same => n,Hangup()

exten => 101,1,Dial(PJSIP/101)
[from-external]
exten => 777,1,NoOp(Входящий звонок от клиента ${CALLERID(all)})
same => n,Answer()
same => n,Dial(PJSIP/101,20)
same => n,Hangup()
            """,
        "http.conf": f"""[general]
enabled=yes
bindaddr=0.0.0.0
bindport={instance.http_port}
            """,
        "rtp.conf": f"""[general]
rtpstart={instance.rtp_port_start}
rtpend={instance.rtp_port_end}
            """,
        "stasis.conf": """[general]
enabled=no
            """,
        "cdr.conf": f"""[general]
enable=yes
unanswered=yes

; CDR в CSV файл
[csv]
usegmtime=yes
loguniqueid=yes
loguserfield=yes

            ; CDR в MySQL (основной способ)
            ;[mysql]
            ;    dsn={config.ASTERISK_ODBC_ID}
            ;    loguniqueid=yes
            ;    loguserfield=yes
            ;    table={config.MYSQL_CDR_TABLE}

            """,
        #TODO: скорее всего этот файл не работает, нужно прочекать и в случае чего удалить 
        # "cdr_mysql.conf": f"""
            # [global]
            #     hostname={config.HOSTNAME}
            #     dbname={config.MYSQL_DATABASE}
            #     password={config.MYSQL_PASSWORD}
            #     user={config.MYSQL_USER}
            #     port={config.MYSQL_PORT}

            # [{config.ASTERISK_ODBC_ID}]
            #     table={config.MYSQL_CDR_TABLE}
            #     ;timezone=UTC
            
            # """,
        "./drivers/odbc.ini":f"""[{config.DSN}]
Description = MySQL connection to Asterisk
Driver      = MySQL
Database    = {config.MYSQL_DATABASE_CDR}
Server      = {config.MYSQL_CONTAINER_NAME}
User        = {config.MYSQL_ASTERISK_USER}
Password    = {config.MYSQL_ASTERISK_USER_PASSWORD}
Port        = {config.MYSQL_PORT}
        """,
        "./drivers/odbcinst.ini":f"""[MySQL]
Description = ODBC for MySQL
Driver      = /usr/lib/x86_64-linux-gnu/odbc/libmaodbc.so
FileUsage   = 1
        """,
        "res_odbc.conf":f"""[{config.ASTERISK_ODBC_ID}]            ; Имя, которое вы дадите этому линку в Asterisk
enabled => yes
dsn => {config.DSN} ; Должно совпадать с именем в /etc/odbc.ini
username => {config.MYSQL_ASTERISK_USER}
password => {config.MYSQL_ASTERISK_USER_PASSWORD}
pre-connect => yes
        """,
        "cdr_adaptive_odbc.conf":f"""[mysql]
connection={config.ASTERISK_ODBC_ID}  ; Имя из res_odbc.conf
table={config.MYSQL_CDR_TABLE}              ; Имя таблицы в БД
            """,
        
    }
    ASTERISK_UID = 1000 
    ASTERISK_GID = 1000
    for filename, content in configs.items():
        filepath = os.path.join(config_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        # Устанавливаем правильные права
        os.chmod(filepath, 0o777)
        os.chown(filepath, ASTERISK_UID, ASTERISK_GID)
        # try:
        #     os.chown(filepath, 0, 0)
        # except PermissionError:
        #     # Если нет прав на смену владельца, используем sudo
        #     subprocess.run(['sudo', 'chown', f'{0}:{0}', filepath])
    # os.chmod(config_dir, 0o777)

    print(f"Конфиги созданы в {config_dir}")


def start_asterisk_container_by_library(instance: AsteriskInstance, db: Session):
    
    client = docker.from_env()
    
    try:
        image = client.images.get(config.ASTERISK_IMAGE_TAG)
        
    except docker.errors.ImageNotFound:
        image, logs = client.images.build(path=config.ASTERISK_IMAGE_PATH, tag=config.ASTERISK_IMAGE_TAG)
    
    base_path = os.path.abspath(instance.config_path)
    try:
        port_bindings = {
        f'{instance.sip_port}/udp': instance.sip_port,
        f'{instance.sip_port}/tcp': instance.sip_port,
        f'{instance.http_port}/tcp': instance.http_port,
        }
        
        # Добавляем RTP порты (диапазон)
        rtp_ports = {}
        for port in range(instance.rtp_port_start, instance.rtp_port_end + 1):
            rtp_ports[f'{port}/udp'] = port
        
        # Объединяем все порты
        port_bindings.update(rtp_ports)
        
        container = client.containers.run(
            image=image,
            name=f"{instance.name}",
            detach=True,
            privileged=True,
            ports=port_bindings,
            network='ceph-asterisk_default',
            # Монтирование томов (Volumes)
            volumes={
                f'{base_path}': {'bind': '/etc/asterisk', 'mode': 'rw'},
                f'{base_path}/sounds': {'bind': '/var/lib/asterisk/sounds/en', 'mode': 'ro'},
                f'{base_path}/drivers/odbc.ini': {'bind': '/etc/odbc.ini', 'mode': 'ro'},
                f'{base_path}/drivers/odbcinst.ini': {'bind': '/etc/odbcinst.ini', 'mode': 'ro'}
            }
        )
        instance.status = "running"
        db.commit()
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
    # Create docker-compose.yml
    compose_config = {
        "version": "3.8",
        "services": {
            f"{instance.name}": {
                "build": ".",
                "container_name": f"asterisk-{instance.name}",
                "ports": [
                    f"{instance.sip_port}:{instance.sip_port}/udp",
                    f"{instance.http_port}:{instance.http_port}/tcp",
                    f"{instance.rtp_port_start}-{instance.rtp_port_end}:{instance.rtp_port_start}-{instance.rtp_port_end}/udp"
                ],
                "volumes": [
                    f"{os.path.abspath(instance.config_path)}:/etc/asterisk:rw",
                    f"{os.path.abspath(instance.config_path)}/sounds:/var/lib/asterisk/sounds/en:ro",
                    f"{os.path.abspath(instance.config_path)}/drivers/odbc.ini:/etc/odbc.ini",
                    f"{os.path.abspath(instance.config_path)}/drivers/odbcinst.ini:/etc/odbcinst.ini"
                ],
                "networks": ["ceph-asterisk_default"],
                "privileged": True,
            }
        },
        # Добавляем этот блок:
        "networks": {
            "ceph-asterisk_default": {
                "external": True
            }
        }
    }

    compose_path = f"./docker-compose/"
    os.makedirs(compose_path, exist_ok=True)

    filename = f"docker-compose-{instance.name}.yml"
    with open(f"{compose_path}/{filename}", "w") as f:
        yaml.dump(compose_config, f)

    # Перед запуском проверяем что файлы созданы
    print(f"Проверка конфигов в {instance.config_path}:")
    for file in os.listdir(instance.config_path):
        filepath = os.path.join(instance.config_path, file)
        if os.path.isfile(filepath):
            print(f"  {file} - {os.path.getsize(filepath)} bytes")

    # Запускаем контейнер
    result = subprocess.run(
        ["docker", "compose","-f",filename, "up", "-d"],
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
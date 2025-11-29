import shutil
import subprocess
from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import docker
import os
import yaml
import json
from sqlalchemy import (
    Boolean,
    DateTime,
    UniqueConstraint,
    create_engine,
    Column,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import text
import random
from datetime import datetime, timedelta

from models import (
    SIPUserCreate,
    CDRRecord,
    ActiveCall,
    CallFilter,
    SIPUserResponse,
    CDRRecordWithUsers,
    AsteriskInstanceCreate,
    AsteriskInstanceResponse,
    ConfigUpdate,
    SIPUserUpdate,
)


# Database setup
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:secret@localhost/asterisk"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Database Models
class AsteriskInstance(Base):
    __tablename__ = "asterisk_instances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    sip_port = Column(Integer, unique=True)
    http_port = Column(Integer, unique=True)
    config_path = Column(Text)
    status = Column(String(20), default="stopped")


Base.metadata.create_all(bind=engine)

class AsteriskInstanceUpdate(BaseModel):
    name: Optional[str] = None
    sip_port: Optional[int] = None
    http_port: Optional[int] = None
    status: Optional[str] = None

class SIPUser(Base):
    __tablename__ = "sip_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), nullable=False)  # SIP username (1001, 1002 и т.д.)
    password = Column(String(80), nullable=False)  # SIP password
    caller_id = Column(String(80), default="")  # Отображаемое имя
    account_code = Column(String(20), default="")  # Код аккаунта по умолчанию
    context = Column(String(80), default="internal")  # Контекст диалплана
    instance_name = Column(String(100), nullable=False)  # К какому инстансу принадлежит
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Уникальный индекс на username + instance_name
    __table_args__ = (
        UniqueConstraint("username", "instance_name", name="uix_username_instance"),
    )


# Создаем таблицу (добавьте в существующий Base.metadata.create_all)
Base.metadata.create_all(bind=engine)
# Docker client
docker_client = docker.from_env()
app = FastAPI(title="Asterisk Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"],  # Vue dev server порты
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/cdr/", response_model=List[CDRRecord])
async def get_cdr_history(
    instance_name: Optional[str] = None,
    src: Optional[str] = None,
    dst: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Получение истории звонков с фильтрацией"""
    query = "SELECT * FROM cdr WHERE 1=1"
    params = {}

    if instance_name:
        query += " AND instance_name = :instance_name"
        params["instance_name"] = instance_name

    if src:
        query += " AND src LIKE :src"
        params["src"] = f"%{src}%"

    if dst:
        query += " AND dst LIKE :dst"
        params["dst"] = f"%{dst}%"

    if date_from:
        query += " AND calldate >= :date_from"
        params["date_from"] = date_from

    if date_to:
        query += " AND calldate <= :date_to"
        params["date_to"] = date_to

    query += " ORDER BY calldate DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = db.execute(text(query), params)
    records = result.fetchall()

    return [row_to_dict(record) for record in records]


def row_to_dict(row):
    """Преобразование SQLAlchemy Row в словарь"""
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    elif hasattr(row, "_asdict"):
        return row._asdict()
    else:
        return dict(row)


@app.get("/cdr/active/", response_model=List[ActiveCall])
async def get_active_calls(
    instance_name: Optional[str] = None, db: Session = Depends(get_db)
):
    """Получение списка активных звонков"""
    query = "SELECT * FROM active_calls WHERE 1=1"
    params = {}

    if instance_name:
        query += " AND instance_name = :instance_name"
        params["instance_name"] = instance_name

    result = db.execute(text(query), params)
    calls = result.fetchall()

    return [row_to_dict(call) for call in calls]


@app.get("/cdr/stats/")
async def get_call_stats(
    instance_name: str,
    period: str = "day",  # day, week, month
    db: Session = Depends(get_db),
):
    """Получение статистики звонков"""

    if period == "day":
        interval = "1 DAY"
    elif period == "week":
        interval = "7 DAY"
    else:
        interval = "30 DAY"

    query = (
        """
    SELECT 
        COUNT(*) as total_calls,
        SUM(duration) as total_duration,
        AVG(duration) as avg_duration,
        SUM(billsec) as total_billsec,
        AVG(billsec) as avg_billsec,
        disposition,
        COUNT(CASE WHEN disposition = 'ANSWERED' THEN 1 END) as answered_calls,
        COUNT(CASE WHEN disposition = 'NO ANSWER' THEN 1 END) as no_answer_calls,
        COUNT(CASE WHEN disposition = 'BUSY' THEN 1 END) as busy_calls,
        COUNT(CASE WHEN disposition = 'FAILED' THEN 1 END) as failed_calls
    FROM cdr 
    WHERE instance_name = :instance_name 
    AND calldate >= NOW() - INTERVAL """
        + interval
        + """
    GROUP BY disposition
    """
    )

    result = db.execute(text(query), {"instance_name": instance_name})
    stats = result.fetchall()

    return {
        "period": period,
        "instance_name": instance_name,
        "stats": [row_to_dict(stat) for stat in stats],
    }


@app.post("/instances/{instance_id}/users", response_model=SIPUserResponse)
async def create_sip_user(
    instance_id: int, user: SIPUserCreate, db: Session = Depends(get_db)
):
    """Создание SIP пользователя"""
    # Проверяем существование инстанса
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Проверяем, что username уникален в рамках инстанса
    existing_user = (
        db.query(SIPUser)
        .filter(
            SIPUser.username == user.username, SIPUser.instance_name == instance.name
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400, detail="Username already exists for this instance"
        )

    # Создаем пользователя
    db_user = SIPUser(
        username=user.username,
        password=user.password,
        caller_id=user.caller_id,
        account_code=user.account_code,
        context=user.context,
        instance_name=instance.name,  # Используем имя инстанса, а не ID
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Обновляем sip.conf
    await update_sip_config(instance.name, db)

    return db_user


# @app.get("/instances/{instance_id}/users", response_model=List[SIPUserResponse])
# async def get_sip_users(
#     instance_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
# ):
#     """Получение списка SIP пользователей инстанса"""
#     instance = (
#         db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
#     )
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")

#     users = (
#         db.query(SIPUser)
#         .filter(SIPUser.instance_name == instance.name)
#         .offset(skip)
#         .limit(limit)
#         .all()
#     )

#     return users


@app.get("/instances/{instance_id}/users/{user_id}", response_model=SIPUserResponse)
async def get_sip_user(instance_id: int, user_id: int, db: Session = Depends(get_db)):
    """Получение конкретного SIP пользователя"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    user = (
        db.query(SIPUser)
        .filter(SIPUser.id == user_id, SIPUser.instance_name == instance.name)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@app.put("/instances/{instance_id}/users/{user_id}", response_model=SIPUserResponse)
async def update_sip_user(
    instance_id: int,
    user_id: int,
    user_update: SIPUserUpdate,
    db: Session = Depends(get_db),
):
    """Обновление SIP пользователя"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    user = (
        db.query(SIPUser)
        .filter(SIPUser.id == user_id, SIPUser.instance_name == instance.name)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Обновляем только переданные поля
    update_data = user_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    # Обновляем sip.conf
    await update_sip_config(instance.name, db)

    return user


@app.delete("/instances/{instance_id}/users/{user_id}")
async def delete_sip_user(
    instance_id: int, user_id: int, db: Session = Depends(get_db)
):
    """Удаление SIP пользователя"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    user = (
        db.query(SIPUser)
        .filter(SIPUser.id == user_id, SIPUser.instance_name == instance.name)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    # Обновляем sip.conf
    await update_sip_config(instance.name, db)

    return {"message": "User deleted successfully"}


async def update_sip_config(instance_name: str, db: Session):
    """Обновление sip.conf на основе пользователей из базы (локальная версия)"""

    # Получаем всех активных пользователей для инстанса
    users = (
        db.query(SIPUser)
        .filter(SIPUser.instance_name == instance_name, SIPUser.is_active == True)
        .all()
    )

    # Получаем порт инстанса
    instance = (
        db.query(AsteriskInstance)
        .filter(AsteriskInstance.name == instance_name)
        .first()
    )
    if not instance:
        print(f"Instance {instance_name} not found in database")
        return

    # Формируем содержимое sip.conf
    sip_conf_content = f"""[general]
context=default
bindaddr=0.0.0.0
bindport={instance.sip_port}
srvlookup=yes
udpbindaddr=0.0.0.0:{instance.sip_port}
transport=udp
disallow=all
allow=ulaw
allow=alaw

"""

    # Добавляем секции для каждого пользователя
    for user in users:
        sip_conf_content += f"""; Пользователь: {user.caller_id}
[{user.username}]
type=friend
host=dynamic
secret={user.password}
context={user.context}
callerid="{user.caller_id}" <{user.username}>
accountcode={user.account_code}
disallow=all
allow=ulaw
allow=alaw
dtmfmode=rfc2833
qualify=yes

"""

    try:
        # Определяем путь к конфигурационной директории инстанса
        config_dir = instance.config_path

        # Если config_path не установлен (для старых инстансов), используем стандартный путь
        if not config_dir or config_dir.startswith("ceph://"):
            config_dir = f"./asterisk_configs/{instance_name}"

        # Создаем директорию если не существует
        os.makedirs(config_dir, exist_ok=True)

        # Сохраняем sip.conf в локальную файловую систему
        sip_conf_path = os.path.join(config_dir, "sip.conf")
        with open(sip_conf_path, "w", encoding="utf-8") as f:
            f.write(sip_conf_content)

        print(f"SIP config updated for {instance_name} at {sip_conf_path}")

        # Перезагружаем SIP конфигурацию в Asterisk
        await reload_asterisk_sip(instance_name)

    except Exception as e:
        print(f"Error updating SIP config for {instance_name}: {e}")


async def reload_asterisk_sip(instance_name: str):
    """Перезагрузка SIP конфигурации в Asterisk"""
    try:
        # Проверяем, запущен ли контейнер
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name=asterisk-{instance_name}"],
            capture_output=True,
            text=True,
        )

        if not result.stdout.strip():
            print(f"Container asterisk-{instance_name} is not running")
            return

        # Выполняем reload SIP в контейнере
        result = subprocess.run(
            [
                "docker",
                "exec",
                f"asterisk-{instance_name}",
                "asterisk",
                "-rx",
                "sip reload",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"Error reloading SIP for {instance_name}: {result.stderr}")
        else:
            print(f"SIP configuration reloaded for {instance_name}")

    except subprocess.TimeoutExpired:
        print(f"Timeout reloading SIP for {instance_name}")
    except FileNotFoundError:
        print(
            f"docker command not found or container not available for {instance_name}"
        )
    except Exception as e:
        print(f"Error reloading SIP for {instance_name}: {e}")


@app.get("/instances/{instance_id}/users", response_model=List[SIPUserResponse])
async def get_sip_users(instance_id: int, db: Session = Depends(get_db)):
    """Получение списка SIP пользователей инстанса"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    users = db.query(SIPUser).filter(SIPUser.instance_name == instance.name).all()
    return users


@app.post("/instances/", response_model=AsteriskInstanceResponse)
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

@app.put("/instances/{instance_id}", response_model=AsteriskInstanceResponse)
async def update_instance(
    instance_id: int, 
    instance_update: AsteriskInstanceUpdate, 
    db: Session = Depends(get_db)
):
    """Обновление экземпляра Asterisk"""
    instance = db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
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
                "restart": "unless-stopped",
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


@app.get("/instances/", response_model=List[AsteriskInstanceResponse])
def list_instances(db: SessionLocal = Depends(get_db)):
    return db.query(AsteriskInstance).all()


@app.get("/instances/{instance_id}", response_model=AsteriskInstanceResponse)
async def get_instance(instance_id: int, db: Session = Depends(get_db)):
    """Получение информации о конкретном экземпляре"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


@app.post("/instances/{instance_id}/reload")
async def reload_instance(instance_id: int, db: Session = Depends(get_db)):
    """Перезагрузка конфигурации Asterisk"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Execute reload command in container
        result = subprocess.run(
            [
                "docker",
                "exec",
                f"asterisk-{instance.name}",
                "asterisk",
                "-rx",
                "reload",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return {"message": "Configuration reloaded successfully"}
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to reload: {result.stderr}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reloading configuration: {str(e)}"
        )


@app.put("/instances/{instance_id}/config")
async def update_config(
    instance_id: int, config_update: ConfigUpdate, db: Session = Depends(get_db)
):
    """Обновление конфигурационного файла"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    config_file = f"{instance.config_path}/{config_update.config_type}.conf"

    try:
        with open(config_file, "w") as f:
            f.write(config_update.content)
        return {
            "message": f"Config {config_update.config_type}.conf updated successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update config: {str(e)}"
        )


@app.delete("/instances/{instance_id}")
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
                timeout=30
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
                    print(f"Warning: Could not remove config directory {config_path}: {e}")
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
                print(f"Warning: Could not remove compose directory {compose_path}: {e}")
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


@app.get("/instances/{instance_id}/config/{config_type}")
async def get_config(instance_id: int, config_type: str, db: Session = Depends(get_db)):
    """Получение содержимого конфигурационного файла"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    config_file = f"{instance.config_path}/{config_type}.conf"

    try:
        with open(config_file, "r") as f:
            content = f.read()
        return {"config_type": config_type, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Config file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")


@app.post("/cdr/simulate/")
async def simulate_calls(
    instance_name: str, count: int = 5, db: Session = Depends(get_db)
):
    """Симуляция тестовых звонков"""

    extensions = ["6001", "6002", "6003", "6004", "6005"]
    dispositions = ["ANSWERED", "NO ANSWER", "BUSY", "FAILED"]

    simulated_calls = []

    for i in range(count):
        # Генерируем случайные данные звонка
        call_date = datetime.now() - timedelta(hours=random.randint(0, 24 * 7))
        src = random.choice(extensions)
        dst = random.choice([e for e in extensions if e != src])
        duration = random.randint(0, 300)
        billsec = random.randint(0, duration)
        disposition = random.choice(dispositions)

        # Вставляем тестовый CDR
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
            "clid": f'"{random.choice(["John", "Jane", "Mike", "Sarah"])}" <{src}>',
            "src": src,
            "dst": dst,
            "dcontext": "local",
            "channel": f"SIP/{src}-0000000{random.randint(1, 9)}",
            "dstchannel": f"SIP/{dst}-0000000{random.randint(1, 9)}",
            "lastapp": "Dial",
            "lastdata": f"SIP/{dst},20",
            "duration": duration,
            "billsec": billsec,
            "disposition": disposition,
            "amaflags": 0,
            "accountcode": "",
            "uniqueid": f"{int(call_date.timestamp())}.{random.randint(1000, 9999)}",
            "userfield": "simulated_call",
            "instance_name": instance_name,
        }

        db.execute(text(query), params)
        simulated_calls.append(params)

    db.commit()

    return {
        "message": f"Simulated {count} calls for {instance_name}",
        "simulated_calls": simulated_calls,
    }


@app.post("/instances/{instance_id}/simulate-call")
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

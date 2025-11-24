import shutil
import subprocess
from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import docker
import os
import yaml
import json
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

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


# Pydantic Models
class AsteriskInstanceCreate(BaseModel):
    name: str
    sip_port: int
    http_port: int


class AsteriskInstanceResponse(BaseModel):
    id: int
    name: str
    sip_port: int
    http_port: int
    status: str

    class Config:
        orm_mode = True


class ConfigUpdate(BaseModel):
    config_type: str  # sip, extensions, etc.
    content: str


# Docker client
docker_client = docker.from_env()
app = FastAPI(title="Asterisk Manager")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/instances/", response_model=AsteriskInstanceResponse)
async def create_instance(
    instance: AsteriskInstanceCreate,
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

        return db_instance

    except Exception as e:
        # Cleanup on error
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)
        raise HTTPException(
            status_code=500, detail=f"Failed to create instance: {str(e)}"
        )


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
def delete_instance(instance_id: int, db: SessionLocal = Depends(get_db)):
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Stop and remove container
    os.system(f"cd /tmp/asterisk-{instance.name} && docker-compose down")

    # Cleanup
    import shutil

    shutil.rmtree(instance.config_path)
    shutil.rmtree(f"/tmp/asterisk-{instance.name}")

    db.delete(instance)
    db.commit()

    return {"message": "Instance deleted"}


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

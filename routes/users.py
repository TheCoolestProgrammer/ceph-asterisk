from datetime import datetime
import os
import subprocess
from fastapi import APIRouter, Depends, HTTPException, status, Path

from database import get_db, get_cdr_db
from models.asterisk_instance import AsteriskInstance
from models.sip_user import PjsipEndpoint, PjsipAor, PjsipAuth
from schemas.asterisk import SIPUserCreate, SIPUserResponse, SIPUserUpdate
from sqlalchemy.orm import Session
from schemas.sip import SIPUserCreate
router = APIRouter(prefix="/instances/{instance_id}/users")




@router.post("/")
def create_sip_user(user_data: SIPUserCreate, 
                    instance_id:int = Path(...), 
                    db: Session = Depends(get_db),
                    cdr_db: Session = Depends(get_cdr_db)):
    # Проверяем, нет ли уже такого пользователя
    instance = db.query(AsteriskInstance).filter(AsteriskInstance.id==instance_id).first()
    if not instance:
        raise HTTPException(status_code=400, detail="instance does not exists")
    
    existing = cdr_db.query(PjsipEndpoint)\
        .join(PjsipAor, PjsipEndpoint.aors == PjsipAor.id)\
        .filter(PjsipEndpoint.id == user_data.username)\
        .filter(PjsipAor.reg_server == instance.name)\
        .first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    

    try:
        # 1. Создаем AOR (регистрация)
        new_aor = PjsipAor(
            id=f"{user_data.username}-aor",
            max_contacts=user_data.max_contacts,
            reg_server=instance.name
        )
        
        # 2. Создаем Auth (пароль)
        new_auth = PjsipAuth(
            id=f"{user_data.username}-auth",
            username=user_data.username,
            password=user_data.password
        )
        
        # 3. Создаем Endpoint (логика)
        new_endpoint = PjsipEndpoint(
            id=user_data.username,
            aors=f"{user_data.username}-aor",
            auth=f"{user_data.username}-auth",
            context=user_data.context,
            transport=f"transport-{user_data.transport.value}"
        )

        cdr_db.add(new_aor)
        cdr_db.add(new_auth)
        cdr_db.add(new_endpoint)
        cdr_db.commit()
        
        return {"status": "success", "username": user_data.username}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# @router.get("/{user_id}", response_model=SIPUserResponse)
# async def get_sip_user(instance_id: int, user_id: int, db: Session = Depends(get_db)):
#     """Получение конкретного SIP пользователя"""
#     instance = (
#         db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
#     )
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")

#     user = (
#         db.query(SIPUser)
#         .filter(SIPUser.id == user_id, SIPUser.instance_name == instance.name)
#         .first()
#     )

#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     return user


# @router.put("/{user_id}", response_model=SIPUserResponse)
# async def update_sip_user(
#     instance_id: int,
#     user_id: int,
#     user_update: SIPUserUpdate,
#     db: Session = Depends(get_db),
# ):
#     """Обновление SIP пользователя"""
#     instance = (
#         db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
#     )
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")

#     user = (
#         db.query(SIPUser)
#         .filter(SIPUser.id == user_id, SIPUser.instance_name == instance.name)
#         .first()
#     )

#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # Обновляем только переданные поля
#     update_data = user_update.dict(exclude_unset=True)
#     for field, value in update_data.items():
#         setattr(user, field, value)

#     user.updated_at = datetime.utcnow()
#     db.commit()
#     db.refresh(user)

#     # Обновляем sip.conf
#     await update_sip_config(instance.name, db)

#     return user


# @router.delete("/{user_id}")
# async def delete_sip_user(
#     instance_id: int, user_id: int, db: Session = Depends(get_db)
# ):
#     """Удаление SIP пользователя"""
#     instance = (
#         db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
#     )
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")

#     user = (
#         db.query(SIPUser)
#         .filter(SIPUser.id == user_id, SIPUser.instance_name == instance.name)
#         .first()
#     )

#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     db.delete(user)
#     db.commit()

#     # Обновляем sip.conf
#     await update_sip_config(instance.name, db)

#     return {"message": "User deleted successfully"}


# async def update_sip_config(instance_name: str, db: Session):
#     """Обновление sip.conf на основе пользователей из базы (локальная версия)"""

#     # Получаем всех активных пользователей для инстанса
#     users = (
#         db.query(SIPUser)
#         .filter(SIPUser.instance_name == instance_name, SIPUser.is_active == True)
#         .all()
#     )

#     # Получаем порт инстанса
#     instance = (
#         db.query(AsteriskInstance)
#         .filter(AsteriskInstance.name == instance_name)
#         .first()
#     )
#     if not instance:
#         print(f"Instance {instance_name} not found in database")
#         return

#     # Формируем содержимое sip.conf
#     sip_conf_content = f"""[general]
#         context=default
#         bindaddr=0.0.0.0
#         bindport={instance.sip_port}
#         srvlookup=yes
#         udpbindaddr=0.0.0.0:{instance.sip_port}
#         transport=udp
#         disallow=all
#         allow=ulaw
#         allow=alaw

#         """

#     # Добавляем секции для каждого пользователя
#     for user in users:
#         sip_conf_content += f"""; Пользователь: {user.caller_id}
#             [{user.username}]
#             type=friend
#             host=dynamic
#             secret={user.password}
#             context={user.context}
#             callerid="{user.caller_id}" <{user.username}>
#             accountcode={user.account_code}
#             disallow=all
#             allow=ulaw
#             allow=alaw
#             dtmfmode=rfc2833
#             qualify=yes

#             """

#     try:
#         # Определяем путь к конфигурационной директории инстанса
#         config_dir = instance.config_path

#         # Если config_path не установлен (для старых инстансов), используем стандартный путь
#         if not config_dir or config_dir.startswith("ceph://"):
#             config_dir = f"./asterisk_configs/{instance_name}"

#         # Создаем директорию если не существует
#         os.makedirs(config_dir, exist_ok=True)

#         # Сохраняем sip.conf в локальную файловую систему
#         sip_conf_path = os.path.join(config_dir, "sip.conf")
#         with open(sip_conf_path, "w", encoding="utf-8") as f:
#             f.write(sip_conf_content)

#         print(f"SIP config updated for {instance_name} at {sip_conf_path}")

#         # Перезагружаем SIP конфигурацию в Asterisk
#         await reload_asterisk_sip(instance_name)

#     except Exception as e:
#         print(f"Error updating SIP config for {instance_name}: {e}")


# async def reload_asterisk_sip(instance_name: str):
#     """Перезагрузка SIP конфигурации в Asterisk"""
#     try:
#         # Проверяем, запущен ли контейнер
#         result = subprocess.run(
#             ["docker", "ps", "-q", "-f", f"name=asterisk-{instance_name}"],
#             capture_output=True,
#             text=True,
#         )

#         if not result.stdout.strip():
#             print(f"Container asterisk-{instance_name} is not running")
#             return

#         # Выполняем reload SIP в контейнере
#         result = subprocess.run(
#             [
#                 "docker",
#                 "exec",
#                 f"asterisk-{instance_name}",
#                 "asterisk",
#                 "-rx",
#                 "sip reload",
#             ],
#             capture_output=True,
#             text=True,
#             timeout=30,
#         )

#         if result.returncode != 0:
#             print(f"Error reloading SIP for {instance_name}: {result.stderr}")
#         else:
#             print(f"SIP configuration reloaded for {instance_name}")

#     except subprocess.TimeoutExpired:
#         print(f"Timeout reloading SIP for {instance_name}")
#     except FileNotFoundError:
#         print(
#             f"docker command not found or container not available for {instance_name}"
#         )
#     except Exception as e:
#         print(f"Error reloading SIP for {instance_name}: {e}")


# @router.get("/", response_model=list[SIPUserResponse])
# async def get_sip_users(instance_id: int, db: Session = Depends(get_db)):
#     """Получение списка SIP пользователей инстанса"""
#     instance = (
#         db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
#     )
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")

#     users = db.query(SIPUser).filter(SIPUser.instance_name == instance.name).all()
#     return users


# @router.post("/", response_model=SIPUserResponse)
# async def create_sip_user(
#     instance_id: int, user: SIPUserCreate, db: Session = Depends(get_db)
# ):
#     """Создание SIP пользователя"""
#     # Проверяем существование инстанса
#     instance = (
#         db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
#     )
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")

#     # Проверяем, что username уникален в рамках инстанса
#     existing_user = (
#         db.query(SIPUser)
#         .filter(
#             SIPUser.username == user.username, SIPUser.instance_name == instance.name
#         )
#         .first()
#     )

#     if existing_user:
#         raise HTTPException(
#             status_code=400, detail="Username already exists for this instance"
#         )

#     # Создаем пользователя
#     db_user = SIPUser(
#         username=user.username,
#         password=user.password,
#         caller_id=user.caller_id,
#         account_code=user.account_code,
#         context=user.context,
#         instance_name=instance.name,  # Используем имя инстанса, а не ID
#     )

#     db.add(db_user)
#     db.commit()
#     db.refresh(db_user)

#     # Обновляем sip.conf
#     await update_sip_config(instance.name, db)

#     return db_user


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

from datetime import datetime
import os
import subprocess
from fastapi import APIRouter, Depends, HTTPException, status, Path

from database import get_db, get_cdr_db
from models.asterisk_instance import AsteriskInstance
from models.sip_user import PjsipEndpoint, PjsipAor, PjsipAuth
from schemas.asterisk import SIPUserCreate, SIPUserResponse, SIPUserUpdate
from sqlalchemy.orm import Session, joinedload
from schemas.sip import SIPUserCreate,AuthSchema, AorSchema, SIPUserItem,SIPUserResponse, AuthUpdate, AorUpdate, SIPUserUpdate
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
    
    # existing = cdr_db.query(PjsipEndpoint)\
    #     .join(PjsipAor, PjsipEndpoint.aors == PjsipAor.id)\
    #     .filter(PjsipEndpoint.id == user_data.username)\
    #     .filter(PjsipAor.reg_server == instance.name)\
    #     .first()
    # existing = cdr_db.query(PjsipEndpoint)\
    #     .join(PjsipAor, PjsipEndpoint.aors_id==PjsipAor.pk)\
    #     .filter(PjsipAor.reg_server == instance.name)\
    #     .filter()\
    #     .first()
    existing = cdr_db.query(PjsipEndpoint)\
        .options(joinedload(PjsipEndpoint.aors_fk), joinedload(PjsipEndpoint.auths_fk))\
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)\
        .filter(PjsipAor.reg_server == instance.name)\
        .filter(PjsipEndpoint.id==user_data.username)\
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
        cdr_db.add(new_aor)
        cdr_db.add(new_auth)
        cdr_db.flush() 
        # 3. Создаем Endpoint (логика)
        new_endpoint = PjsipEndpoint(
            id=user_data.username,
            aors=f"{user_data.username}-aor",
            auth=f"{user_data.username}-auth",
            auths_id=new_auth.pk,
            aors_id=new_aor.pk,
            context=user_data.context,
            transport=f"transport-{user_data.transport.value}"
        )

        cdr_db.add(new_endpoint)
        cdr_db.commit()
        
        return {"status": "success", "username": user_data.username}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/", response_model=list[SIPUserItem]) # Или SIPUserResponse
async def get_sip_users(instance_id: int = Path(...),
                        db: Session = Depends(get_db),
                        cdr_db: Session = Depends(get_cdr_db)):
    
    instance = db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=400, detail="instance does not exists")
    
    numbers = cdr_db.query(PjsipEndpoint)\
        .options(joinedload(PjsipEndpoint.aors_fk), joinedload(PjsipEndpoint.auths_fk))\
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)\
        .filter(PjsipAor.reg_server == instance.name)\
        .all()
    
    return numbers

@router.get("/{endpoint_id}", response_model=SIPUserItem) #под username понимается номер аля 101
async def get_sip_user(endpoint_id: str = Path(...),
                        instance_id: int = Path(...),
                        db: Session = Depends(get_db),
                        cdr_db: Session = Depends(get_cdr_db)):
    
    instance = db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=400, detail="instance does not exists")
    
    number = cdr_db.query(PjsipEndpoint)\
        .options(joinedload(PjsipEndpoint.aors_fk), joinedload(PjsipEndpoint.auths_fk))\
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)\
        .filter(PjsipAor.reg_server == instance.name)\
        .filter(PjsipEndpoint.id==endpoint_id)\
        .first() #в случае чего можно заменить на PjsipAuth.id==username
    
    return number
@router.put("/{endpoint_id}", response_model=SIPUserItem)
async def update_sip_user_by_creds(
    update_data: SIPUserUpdate,
    endpoint_id: str = Path(...),   # SIP логин (например '101')
    instance_id: int = Path(...),
    cdr_db: Session = Depends(get_cdr_db),
    db:Session=Depends(get_db)
):
    instance = db.query(AsteriskInstance).filter(AsteriskInstance.id==instance_id).first()
    if not instance:
        raise HTTPException(status_code=400, detail="instance does not exists")

    # 1. Поиск по связанным таблицам
    endpoint = cdr_db.query(PjsipEndpoint)\
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)\
        .join(PjsipAuth, PjsipEndpoint.auths_id == PjsipAuth.pk)\
        .options(joinedload(PjsipEndpoint.aors_fk), joinedload(PjsipEndpoint.auths_fk))\
        .filter(PjsipAor.reg_server == instance.name)\
        .filter(PjsipEndpoint.id == endpoint_id)\
        .first()

    if not endpoint:
        raise HTTPException(
            status_code=404, 
            detail=f"User with id '{endpoint_id}' on server '{instance.name}' not found"
        )

    try:
        # 2. Обновление полей самого Endpoint (transport, context и т.д.)
        endpoint_dict = update_data.model_dump(exclude={'auth', 'aor'}, exclude_unset=True)
        for key, value in endpoint_dict.items():
            setattr(endpoint, key, value)

        # 3. Обновление связанных данных Auth (если прислали)
        if update_data.auth:
            auth_dict = update_data.auth.model_dump(exclude_unset=True)
            for key, value in auth_dict.items():
                setattr(endpoint.auths_fk, key, value)

        # 4. Обновление связанных данных AOR (если прислали)
        if update_data.aor:
            aor_dict = update_data.aor.model_dump(exclude_unset=True)
            for key, value in aor_dict.items():
                setattr(endpoint.aors_fk, key, value)

        cdr_db.commit()
        cdr_db.refresh(endpoint)
        return endpoint

    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.delete("/delete/{endpoint_id}", status_code=200)
async def delete_sip_user(
    instance_id: int=Path(...), 
    endpoint_id: str=Path(...), 
    cdr_db: Session = Depends(get_cdr_db),
    db:Session=Depends(get_db)
):
    instance = db.query(AsteriskInstance).filter(AsteriskInstance.id==instance_id).first()
    if not instance:
        raise HTTPException(status_code=400, detail="instance does not exists")

    # 1. Ищем Endpoint, чтобы получить доступ к связанным ID (auth и aor)
    endpoint = cdr_db.query(PjsipEndpoint)\
        .join(PjsipAor, PjsipEndpoint.aors_id == PjsipAor.pk)\
        .join(PjsipAuth, PjsipEndpoint.auths_id == PjsipAuth.pk)\
        .filter(PjsipAor.reg_server == instance.name)\
        .filter(PjsipEndpoint.id== endpoint_id)\
        .first()

    if not endpoint:
        raise HTTPException(
            status_code=404, 
            detail=f"User {endpoint_id} on server {instance.name} not found"
        )

    try:
        # 2. Сохраняем ссылки на связанные объекты перед удалением основного
        # Это нужно, если в БД не настроен автоматический каскад на уровне таблиц
        auth_obj = endpoint.auths_fk
        aor_obj = endpoint.aors_fk

        # 3. Удаляем Endpoint (главную запись)
        cdr_db.delete(endpoint)
        
        # 4. Вручную удаляем связанные записи, если они не удалились каскадом БД
        if auth_obj:
            cdr_db.delete(auth_obj)
        if aor_obj:
            cdr_db.delete(aor_obj)

        cdr_db.commit()
        return {"message":"success"} # При 204 коде тело ответа не возвращается

    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


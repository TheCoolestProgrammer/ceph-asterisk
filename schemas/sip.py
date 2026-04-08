from pydantic import BaseModel, ConfigDict
from schemas.asterisk import TransportType
from typing import Optional

class SIPUserCreate(BaseModel):
    username: str
    password: str
    context: str = "from-internal"
    max_contacts: int = 1
    transport: TransportType = TransportType.UDP

class AuthSchema(BaseModel):
    pk: int
    id: str
    auth_type: str
    username: Optional[str]
    # password обычно не возвращаем на фронт в общем списке из соображений безопасности
    
    model_config = ConfigDict(from_attributes=True)

class AorSchema(BaseModel):
    pk: int
    id: str
    reg_server: Optional[str]
    max_contacts: int
    
    model_config = ConfigDict(from_attributes=True)

class SIPUserItem(BaseModel):
    pk: int
    id: str  # Это ваш номер (например, '101')
    transport: str
    context: str
    allow: str
    disallow: str
    
    # Связи (используем имена из relationship в модели)
    aors_fk: AorSchema
    auths_fk: AuthSchema

    model_config = ConfigDict(from_attributes=True)

# Итоговая схема для response_model
class SIPUserResponse(BaseModel):
    # Если вы возвращаете numbers как .all(), то это список
    users: list[SIPUserItem] 



class AuthUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    auth_type: Optional[str] = 'userpass'

class AorUpdate(BaseModel):
    max_contacts: Optional[int] = 1
    # reg_server обычно не меняем вручную, он привязан к инстансу

class SIPUserUpdate(BaseModel):
    # Поля самого Endpoint
    transport: Optional[str] = None
    context: Optional[str] = None
    disallow: Optional[str] = None
    allow: Optional[str] = None
    
    # Вложенные данные для обновления
    auth: Optional[AuthUpdate] = None
    aor: Optional[AorUpdate] = None
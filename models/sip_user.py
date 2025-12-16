from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from database import Base


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

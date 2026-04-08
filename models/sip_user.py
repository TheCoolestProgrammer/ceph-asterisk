from sqlalchemy import Column, String, Integer, Enum, Text, create_engine, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from database import BaseCDR
import enum

class Choise(enum.Enum):
    YES='yes'
    NO='no'

class PjsipEndpoint(BaseCDR):
    """Основные настройки логики вызовов для пользователя"""
    __tablename__ = 'ps_endpoints'

    pk = Column(Integer, primary_key=True, autoincrement=True)
    # тут стоит пояснить, что id это скорее просто имя
    # а ключ вводится для того, чтобы удобнее детектить дубликаты номеров
    # по двум полям: username(или id) и reg_server и не вводить составной ключ
    id = Column(String(40))  # Имя: '101'
    transport = Column(String(40), default='transport-udp')
    #возможно будет лучше сделать их foreign key
    aors = Column(String(200))                 # Ссылка на ID в ps_aors
    auth = Column(String(40))                 # Ссылка на ID в ps_auths
    # так как эти двое требуют строковое представление,
    # то воодим нормальные ключи
    aors_id = Column(Integer, ForeignKey("ps_aors.pk", ondelete='CASCADE'))
    auths_id = Column(Integer, ForeignKey("ps_auths.pk", ondelete='CASCADE'))

    context = Column(String(40), default='from-internal')
    disallow = Column(String(200), default='all')
    allow = Column(String(200), default='ulaw,alaw')
    direct_media = Column(Enum(Choise), default=Choise.NO)
    rewrite_contact = Column(Enum(Choise), default=Choise.YES)
    rtp_symmetric = Column(Enum(Choise), default=Choise.YES)
    force_rport = Column(Enum(Choise), default=Choise.YES)
    mwi_from_user = Column(String(40))

    aors_fk = relationship("PjsipAor", back_populates="endpoints")
    auths_fk = relationship("PjsipAuth", back_populates="endpoints")

class PjsipAuth(BaseCDR):
    """Логины и пароли"""
    __tablename__ = 'ps_auths'

    pk = Column(Integer, primary_key=True, autoincrement=True)

    id = Column(String(40), primary_key=True)  # Например: '101-auth'
    auth_type = Column(Enum('userpass', 'md5'), default='userpass')
    password = Column(String(80))
    username = Column(String(80))

    endpoints = relationship("PjsipEndpoint", back_populates="auths_fk")

class PjsipAor(BaseCDR):
    """Настройки регистрации (Address of Record)"""
    __tablename__ = 'ps_aors'

    pk = Column(Integer, primary_key=True, autoincrement=True)

    id = Column(String(40), primary_key=True)  # Например: '101-aor'
    reg_server = Column(String(60), nullable=True) # container name
    max_contacts = Column(Integer, default=1)
    remove_existing = Column(Enum(Choise), default=Choise.YES)
    minimum_expiration = Column(Integer, default=60)
    default_expiration = Column(Integer, default=3600)
    qualify_frequency = Column(Integer, default=30)

    endpoints = relationship("PjsipEndpoint", back_populates="aors_fk")


class PjsipContact(BaseCDR):
    """Сюда Asterisk записывает текущие IP адреса онлайн-устройств"""
    __tablename__ = 'ps_contacts'

    id = Column(String(255), primary_key=True)
    uri = Column(String(255))
    expiration_time = Column(String(40))
    qualify_frequency = Column(Integer)
    endpoint = Column(String(40))
    user_agent = Column(String(255))

class PjsipDomainAlias(BaseCDR):
    """Алиасы доменов (если нужно)"""
    __tablename__ = 'ps_domain_aliases'
    id = Column(String(40), primary_key=True)
    domain = Column(String(80))

class PJSIPPSEndpointIdIPS(BaseCDR):
    """ip аддреса"""
    __tablename__ = 'ps_endpoint_id_ips'
    id = Column(String(255), primary_key=True)
    endpoint = Column(String(40),default=None)
    match = Column(String(80),default=None)
    srv_lookups = Column(Enum(Choise), default=Choise.YES)
    match_geader = Column(String(255),default=None)


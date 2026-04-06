from sqlalchemy import Column, String, Integer, Enum, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from database import BaseCDR
import enum

class Choise(enum.Enum):
    YES='yes'
    NO='no'

class PjsipEndpoint(BaseCDR):
    """Основные настройки логики вызовов для пользователя"""
    __tablename__ = 'ps_endpoints'

    id = Column(String(40), primary_key=True)  # Имя: '101'
    transport = Column(String(40), default='transport-udp')
    #возможно будет лучше сделать их foreign key
    aors = Column(String(200))                 # Ссылка на ID в ps_aors
    auth = Column(String(40))                 # Ссылка на ID в ps_auths
    context = Column(String(40), default='from-internal')
    disallow = Column(String(200), default='all')
    allow = Column(String(200), default='ulaw,alaw')
    direct_media = Column(Enum(Choise), default=Choise.NO)
    rewrite_contact = Column(Enum(Choise), default=Choise.YES)
    rtp_symmetric = Column(Enum(Choise), default=Choise.YES)
    force_rport = Column(Enum(Choise), default=Choise.YES)
    mwi_from_user = Column(String(40))

class PjsipAuth(BaseCDR):
    """Логины и пароли"""
    __tablename__ = 'ps_auths'

    id = Column(String(40), primary_key=True)  # Например: '101-auth'
    auth_type = Column(Enum('userpass', 'md5'), default='userpass')
    password = Column(String(80))
    username = Column(String(80))

class PjsipAor(BaseCDR):
    """Настройки регистрации (Address of Record)"""
    __tablename__ = 'ps_aors'

    id = Column(String(40), primary_key=True)  # Например: '101-aor'
    reg_server = Column(String(60), nullable=True) # container name
    max_contacts = Column(Integer, default=1)
    remove_existing = Column(Enum(Choise), default=Choise.YES)
    minimum_expiration = Column(Integer, default=60)
    default_expiration = Column(Integer, default=3600)
    qualify_frequency = Column(Integer, default=30)

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
from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase
import datetime
from database import Base

class CDR(Base):
    __tablename__ = 'asterisk_cdr'

    accountcode = Column(String(80), default='')
    src = Column(String(80), default='')
    dst = Column(String(80), default='')
    dcontext = Column(String(80), default='')
    clid = Column(String(80), default='')
    channel = Column(String(80), default='')
    dstchannel = Column(String(80), default='')
    lastapp = Column(String(80), default='')
    lastdata = Column(String(80), default='')
    start = Column(DateTime, default=datetime.datetime(1970, 1, 1))
    answer = Column(DateTime, default=datetime.datetime(1970, 1, 1))
    end = Column(DateTime, default=datetime.datetime(1970, 1, 1))
    duration = Column(Integer, default=0)
    billsec = Column(Integer, default=0)
    disposition = Column(String(45), default='')
    amaflags = Column(Integer, default=0)
    uniqueid = Column(String(150), primary_key=True, default='')
    userfield = Column(String(255), default='')
    sequence = Column(Integer, default=0)
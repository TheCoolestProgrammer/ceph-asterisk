from sqlalchemy import Column, String, DateTime, Integer
import datetime
from database import BaseCDR

class CDR(BaseCDR):
    __tablename__ = 'asterisk_cdr'

    accountcode = Column(String(80), default='')
    src = Column(String(80), default='') 
    '''who`s number'''
    dst = Column(String(80), default='') 
    '''to whom number'''
    dcontext = Column(String(80), default='') 
    '''context like "from-internal"'''
    clid = Column(String(80), default='') 
    '''caller`s name'''
    channel = Column(String(80), default='') 
    '''PJSIP-101-00000000X'''
    dstchannel = Column(String(80), default='')
    lastapp = Column(String(80), default='')
    '''last reached endpoint like "echo()" or "hangup()"'''
    lastdata = Column(String(80), default='') 
    start = Column(DateTime, default=datetime.datetime(1970, 1, 1))
    answer = Column(DateTime, default=datetime.datetime(1970, 1, 1))
    end = Column(DateTime, default=datetime.datetime(1970, 1, 1))
    duration = Column(Integer, default=0)
    billsec = Column(Integer, default=0)
    disposition = Column(String(45), default='') 
    '''answer code like ANSWERED, NO ANSWER, BUSY'''
    amaflags = Column(Integer, default=0)
    uniqueid = Column(String(150), primary_key=True, default='') 
    '''asterisk instance container name like "name-id"'''
    userfield = Column(String(255), default='')
    sequence = Column(Integer, default=0)
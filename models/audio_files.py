
from sqlalchemy import Column, Integer, String, Date, Float
from database import Base
import datetime
import enum 

class AudioFormat(enum.Enum):
    WAV = "wav"
    GSM = "gsm"
    ALAW = "alaw"
    ULAW = "ulaw"

class AudioFile(Base):
    __tablename__ = "audio_files"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    format = Column(String(5))
    size_kb = Column(Float)
    duration_sec=Column(Integer)
    create_date = Column(Date,default=datetime.datetime.today)

from sqlalchemy import Column, Integer, String, Text
from database import Base


# Database Models
class AsteriskInstance(Base):
    __tablename__ = "asterisk_instances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    sip_port = Column(Integer, unique=True,default=5069)
    http_port = Column(Integer, unique=True, default=8087)
    rtp_port_start = Column(Integer, unique=True, default=10000)
    rtp_port_end = Column(Integer, unique=True, default=10010)
    ami_port = Column(Integer, unique=True, default=5038)
    config_path = Column(Text)
    status = Column(String(20), default="stopped")
    # create_date = Column()
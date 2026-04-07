from pydantic import BaseModel
from schemas.asterisk import TransportType

class SIPUserCreate(BaseModel):
    username: str
    password: str
    context: str = "from-internal"
    max_contacts: int = 1
    transport: TransportType = TransportType.UDP
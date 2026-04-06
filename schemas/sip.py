from pydantic import BaseModel

class SIPUserCreate(BaseModel):
    username: str
    password: str
    context: str = "from-internal"
    max_contacts: int = 1
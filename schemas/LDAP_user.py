from typing import Optional
from pydantic import BaseModel


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    auth_method: str = "local"


class UserInDB(User):
    hashed_password: Optional[str] = None


class LDAPLoginRequest(BaseModel):
    username: str
    password: str

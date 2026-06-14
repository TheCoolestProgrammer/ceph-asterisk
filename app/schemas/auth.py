from pydantic import BaseModel


class UserLogin(BaseModel):
    login: str
    password: str


class UserRegister(BaseModel):
    login: str
    password: str
    name: str


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str


class TokenRefresh(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    user_id: int = None
    login: str = None

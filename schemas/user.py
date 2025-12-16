from pydantic import BaseModel
from typing import Optional

from models.user import Role


class UserBase(BaseModel):
    login: str
    name: str
    role: str = Role.ADMIN


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    login: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int

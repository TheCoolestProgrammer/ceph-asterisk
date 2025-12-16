from sqlalchemy import Column, Integer, String, Enum

from database import Base

import enum


class Role(enum.Enum):
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)

    role = Column(Enum(Role), nullable=False, default=Role.ADMIN)

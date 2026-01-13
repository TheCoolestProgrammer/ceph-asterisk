from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Any, Optional
from config import config

# Явно указываем использование bcrypt_sha256
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode, config.REFRESH_SECRET_KEY, algorithm=config.ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str, is_refresh: bool = False) -> Optional[dict[str, Any]]:
    try:
        secret_key = config.REFRESH_SECRET_KEY if is_refresh else config.SECRET_KEY
        payload = jwt.decode(token, secret_key, algorithms=[config.ALGORITHM])

        token_type = payload.get("type")
        if is_refresh and token_type != "refresh":
            return None
        if not is_refresh and token_type != "access":
            return None

        return payload
    except JWTError:
        return None


def create_tokens(user_id: int, login: str) -> dict[str, str]:
    """Создает пару access и refresh токенов"""
    access_token = create_access_token(data={"user_id": user_id, "login": login})
    refresh_token = create_refresh_token(data={"user_id": user_id, "login": login})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def create_LDAP_tokens(email: str, login: str) -> dict[str, str]:
    """Создает пару access и refresh токенов"""
    access_token = create_access_token(data={"email": email, "login": login})
    refresh_token = create_refresh_token(data={"email": email, "login": login})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

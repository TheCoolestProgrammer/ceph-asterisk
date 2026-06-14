from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.auth import TokenRefresh, UserLogin, UserRegister, Token
from app.schemas.user import UserResponse
from app.core.security import (
    verify_password,
    get_password_hash,
    create_tokens,
    verify_token,
    # create_LDAP_tokens,
)
from app.core.config import config
from app.core.database import get_db
from app.core.ldap_auth import ldap_auth

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _authenticate_user(
    credentials: HTTPAuthorizationCredentials,
    db: Session,
) -> User:
    payload = verify_token(credentials.credentials, is_refresh=False)
    if payload is None:
        raise _credentials_exception

    user_id: int = payload.get("user_id")
    if user_id is None:
        raise _credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _credentials_exception

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    return _authenticate_user(credentials, db)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: Session = Depends(get_db),
) -> None:
    if config.DEV_MODE:
        return

    if credentials is None:
        raise _credentials_exception

    _authenticate_user(credentials, db)


@router.post("/register", response_model=UserResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    if not config.DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled in production",
        )

    existing_user = db.query(User).filter(User.login == user_data.login).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Login already registered"
        )

    hashed_password = get_password_hash(user_data.password)
    user = User(
        login=user_data.login,
        password_hash=hashed_password,
        name=user_data.name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.login == user_data.login).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Создаем пару токенов
    tokens = create_tokens(user_id=user.id, login=user.login)

    return tokens


@router.post("/login/ldap", response_model=Token)
def login_LDAP(user_data: UserLogin, db: Session = Depends(get_db)):
    ldap_user = ldap_auth.authenticate(user_data.login, user_data.password)
    if ldap_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    print(ldap_user)
    user = db.query(User).filter(User.login == user_data.login).first()
    if not user:
        hashed_password = get_password_hash(user_data.password)
        user = User(
            login=user_data.login,
            password_hash=hashed_password,
            name=ldap_user['username']
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        user = db.query(User).filter(User.login == user_data.login).first()

    # Создаем пару токенов
    tokens = create_tokens(user_id=user.id, login=user_data.login)
    return tokens


@router.post("/refresh", response_model=Token)
def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Проверяем refresh токен
    payload = verify_token(token_data.refresh_token, is_refresh=True)
    if payload is None:
        raise credentials_exception

    user_id: int = payload.get("user_id")
    login: str = payload.get("login")

    if user_id is None or login is None:
        raise credentials_exception

    # Проверяем, существует ли пользователь
    user = db.query(User).filter(User.id == user_id, User.login == login).first()
    if user is None:
        raise credentials_exception

    # Создаем новую пару токенов
    tokens = create_tokens(user_id=user.id, login=user.login)

    return tokens


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user

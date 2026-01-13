from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    DATABASE_URL: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"
    SECRET_KEY: str
    REFRESH_SECRET_KEY: str

    LDAP_ENABLED: bool
    LDAP_SERVER: str
    LDAP_PORT: int
    LDAP_USE_SSL: bool
    LDAP_BASE_DN: str
    LDAP_USER_DN_TEMPLATE: str
    LDAP_ADMIN_DN: str
    LDAP_ADMIN_PASSWORD: str
    LDAP_SEARCH_BASE: str
    LDAP_SEARCH_FILTER: str
    LDAP_ATTRIBUTES: list[str] = ["cn", "mail", "displayName", "uid"]

    @field_validator("LDAP_ATTRIBUTES", mode="before")
    @classmethod
    def parse_ldap_attributes(cls, v):
        if isinstance(v, str):
            # Убираем пробелы и разбиваем по запятым
            return [attr.strip() for attr in v.split(",") if attr.strip()]
        return v


config = Config()

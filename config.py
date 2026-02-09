from pydantic import field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env",extra='ignore')
    HOSTNAME:str
    MYSQL_DATABASE:str
    MYSQL_DATABASE_CDR:str
    MYSQL_USER:str
    MYSQL_PASSWORD:str
    MYSQL_ASTERISK_USER:str
    MYSQL_ASTERISK_USER_PASSWORD:str
    MYSQL_PORT:int
    MYSQL_CONTAINER_NAME:str
    MYSQL_CDR_TABLE:str

    ASTERISK_IMAGE_TAG:str
    ASTERISK_IMAGE_PATH:str
    
    ASTERISK_ODBC_ID:str
    DSN:str

    @computed_field
    @property
    def DATABASE_URL(self)->str:
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.HOSTNAME}/{self.MYSQL_DATABASE}"
 
    @computed_field
    @property
    def DATABASE_CDR_URL(self)->str:
        return f"mysql+pymysql://{self.MYSQL_ASTERISK_USER}:{self.MYSQL_ASTERISK_USER_PASSWORD}@{self.HOSTNAME}/{self.MYSQL_DATABASE_CDR}"
 
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

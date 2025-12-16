from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    DATABASE_URL: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
    ALGORITHM: str = "HS256"
    SECRET_KEY: str


config = Config()

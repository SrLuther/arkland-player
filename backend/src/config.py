from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 horas

    SERVER_API_KEY: str
    STEAM_API_KEY: str
    STEAM_OPENID_RETURN_URL: str

    CORS_ORIGINS: List[str] = ["http://localhost"]

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY deve ter pelo menos 32 caracteres")
        return v

    @field_validator("SERVER_API_KEY")
    @classmethod
    def server_key_min_length(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("SERVER_API_KEY deve ter pelo menos 16 caracteres")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

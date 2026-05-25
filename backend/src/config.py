import pathlib
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator

# .env sempre relativo ao diretório deste arquivo (backend/src/../.env = backend/.env)
_ENV_FILE = pathlib.Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 horas

    SERVER_API_KEY: str
    STEAM_API_KEY: str
    STEAM_OPENID_RETURN_URL: str

    CORS_ORIGINS: List[str] = ["http://localhost"]

    # Senha master para elevação de role Dev via Steam
    MASTER_PASSWORD: str = ""

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

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()  # type: ignore[call-arg]

# Credenciais dev — constantes fixas, NUNCA lidas do .env
DEV_USERNAME: str = "dev"
DEV_PASSWORD: str = "AKLserverDEV@"

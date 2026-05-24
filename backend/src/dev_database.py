"""Banco de dados local (SQLite) exclusivo para dados do Dev.

Independente do MySQL — funciona sem conexão de rede.
Armazena: DevUser, SystemConfig, AuditLog.
"""
import pathlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_DEV_DB_PATH = pathlib.Path(__file__).parent.parent / "dev_data.db"

dev_engine = create_engine(
    f"sqlite:///{_DEV_DB_PATH}",
    connect_args={"check_same_thread": False},
)

DevSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=dev_engine)


class DevBase(DeclarativeBase):
    pass


def get_dev_db():
    db = DevSessionLocal()
    try:
        yield db
    finally:
        db.close()

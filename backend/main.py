import json as _json
import os
import pathlib
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import engine, Base, SessionLocal
from src.dev_database import dev_engine, DevBase, DevSessionLocal
from src.routes import auth, inventory, player, admin
from src.routes import bot as bot_routes

_VERSION = (pathlib.Path(__file__).parent.parent / "VERSION").read_text().strip()

# Banco de dados de jogadores (MySQL) — pode estar offline
try:
    Base.metadata.create_all(bind=engine)
except Exception as _e:
    print(f"[WARN] MySQL indisponível na inicialização: {_e}")

# Banco de dados dev (SQLite local) — sempre disponível
DevBase.metadata.create_all(bind=dev_engine)


def _seed_dev_user() -> None:
    """Cria o primeiro usuário DEV a partir de variáveis de ambiente, se configurado."""
    from src.config import settings
    username = settings.DEV_USERNAME
    password = settings.DEV_PASSWORD
    if not username or not password:
        return
    from src import models
    from src.auth import hash_password
    db = DevSessionLocal()
    try:
        if not db.query(models.DevUser).filter_by(username=username).first():
            db.add(models.DevUser(username=username, password_hash=hash_password(password)))
            db.commit()
    except Exception as _e:
        print(f"[WARN] Não foi possível criar usuário dev seed: {_e}")
    finally:
        db.close()


try:
    _seed_dev_user()
except Exception as _e:
    print(f"[WARN] _seed_dev_user falhou: {_e}")


def _seed_system_config() -> None:
    """Cria entradas padrão de SystemConfig se não existirem."""
    from src import models as _m
    db = DevSessionLocal()
    try:
        defaults = {
            "admin_groups": _json.dumps(["admin", "mod", "owner"]),
            "jwt_expire_minutes": str(settings.JWT_EXPIRE_MINUTES),
            "cors_origins": _json.dumps(settings.CORS_ORIGINS),
            "steam_return_url": settings.STEAM_OPENID_RETURN_URL,
        }
        for key, value in defaults.items():
            if not db.query(_m.SystemConfig).filter_by(key=key).first():
                db.add(_m.SystemConfig(key=key, value=value))
        db.commit()
    except Exception as _e:
        print(f"[WARN] Não foi possível criar SystemConfig seed: {_e}")
    finally:
        db.close()


try:
    _seed_system_config()
except Exception as _e:
    print(f"[WARN] _seed_system_config falhou: {_e}")

app = FastAPI(
    title="ARKLAND-Player API",
    version=_VERSION,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Server-Key"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
app.include_router(player.router, prefix="/player", tags=["player"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(bot_routes.router, prefix="/bot", tags=["bot"])


@app.get("/health", tags=["status"])
def health_check():
    return {"status": "ok", "version": _VERSION}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)

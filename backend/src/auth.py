import bcrypt as _bcrypt
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src import models

STEAM_OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
STEAM_ID_PREFIX = "https://steamcommunity.com/openid/id/"

_bearer = HTTPBearer()


# ─── Senha ────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_jwt(sub: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": sub, "role": role, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


@dataclass
class CurrentUser:
    sub: str
    role: str  # "player" | "admin" | "dev"


def _decode_jwt(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        sub: Optional[str] = payload.get("sub")
        # compatibilidade com tokens antigos sem campo role
        role: str = payload.get("role", "player")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        return CurrentUser(sub=sub, role=role)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    return _decode_jwt(credentials.credentials)


def require_role(*roles: str):
    """Dependência que restringe acesso a determinados roles."""
    def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        return current
    return _dep


_DEFAULT_ADMIN_GROUPS: frozenset[str] = frozenset({"admin", "mod", "owner"})


def steam_role(permission_group: str, admin_groups: Optional[frozenset[str]] = None) -> str:
    """Mapeia permission_group do servidor para role JWT."""
    groups = admin_groups if admin_groups is not None else _DEFAULT_ADMIN_GROUPS
    return "admin" if permission_group in groups else "player"


async def verify_steam_openid(params: dict) -> Optional[str]:
    """Verifica o callback do Steam OpenID 2.0 e retorna o SteamID64 ou None."""
    validation_params = {**params, "openid.mode": "check_authentication"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(STEAM_OPENID_ENDPOINT, data=validation_params)
    if "is_valid:true" not in resp.text:
        return None
    claimed_id: str = params.get("openid.claimed_id", "")
    if not claimed_id.startswith(STEAM_ID_PREFIX):
        return None
    return claimed_id[len(STEAM_ID_PREFIX):]


async def get_steam_persona(steam_id: str) -> str:
    """Retorna o nome do jogador via Steam Web API."""
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                params={"key": settings.STEAM_API_KEY, "steamids": steam_id},
            )
        players = resp.json().get("response", {}).get("players", [])
        if players:
            return players[0].get("personaname", steam_id)
    except Exception:
        pass
    return steam_id


def get_or_create_player(
    steam_id: str, persona_name: str, db: Session
) -> models.Player:
    player = db.query(models.Player).filter_by(steam_id=steam_id).first()
    if player:
        player.persona_name = persona_name
        player.last_seen = datetime.now(timezone.utc)
    else:
        player = models.Player(steam_id=steam_id, persona_name=persona_name)
        db.add(player)
    db.commit()
    db.refresh(player)
    return player


def get_current_player(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Player:
    if current.role not in ("player", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    player = db.query(models.Player).filter_by(steam_id=current.sub).first()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogador não encontrado")
    return player

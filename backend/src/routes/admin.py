import json
import time as _time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as _sql_text

from src.database import get_db
from src.dev_database import get_dev_db
from src import auth as auth_utils, models
from src.config import settings

router = APIRouter()

_MODULE_START = _time.time()


@router.get("/players")
def list_players(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("admin", "dev")),
    db: Session = Depends(get_db),
):
    """Lista todos os jogadores registrados. Acesso: admin ou dev."""
    players = db.query(models.Player).order_by(models.Player.last_seen.desc()).all()
    return [
        {
            "id": p.id,
            "steam_id": p.steam_id,
            "persona_name": p.persona_name,
            "permission_group": p.permission_group,
            "last_seen": p.last_seen,
            "created_at": p.created_at,
        }
        for p in players
    ]


@router.get("/stats")
def system_stats(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    db: Session = Depends(get_db),
):
    """Estatísticas básicas (compat.). Acesso: apenas dev."""
    return {
        "total_players": db.query(models.Player).count(),
        "total_snapshots": db.query(models.InventorySnapshot).count(),
        "total_items": db.query(models.InventoryItem).count(),
    }


class _CreateDevUserRequest(BaseModel):
    username: str
    password: str


@router.post("/dev-users")
def create_dev_user(
    body: _CreateDevUserRequest,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Cria um novo usuário Dev. Acesso: apenas dev."""
    if dev_db.query(models.DevUser).filter_by(username=body.username).first():
        raise HTTPException(status_code=409, detail="Usuário já existe")
    dev_db.add(models.DevUser(
        username=body.username,
        password_hash=auth_utils.hash_password(body.password),
    ))
    dev_db.commit()
    return {"message": "Usuário Dev criado com sucesso", "username": body.username}


# ─── Saúde do Sistema ─────────────────────────────────────────────────────────

@router.get("/health")
async def admin_health(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    db: Session = Depends(get_db),
):
    """Status de saúde do sistema. Acesso: apenas dev."""
    try:
        db.execute(_sql_text("SELECT 1"))  # testa MySQL
        db_status = "ok"
    except Exception:
        db_status = "error"

    steam_status = "not_configured"
    if settings.STEAM_API_KEY and settings.STEAM_API_KEY not in ("PREENCHER", ""):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://api.steampowered.com/ISteamWebAPIUtil/GetSupportedAPIList/v1/",
                    params={"key": settings.STEAM_API_KEY},
                )
            steam_status = "ok" if r.status_code == 200 else "error"
        except Exception:
            steam_status = "error"

    import pathlib
    try:
        version = (pathlib.Path(__file__).parent.parent.parent / "VERSION").read_text().strip()
    except Exception:
        version = "?"

    return {
        "backend": "ok",
        "version": version,
        "uptime_seconds": round(_time.time() - _MODULE_START, 1),
        "database": db_status,
        "steam_api": steam_status,
    }


# ─── Usuários Dev ─────────────────────────────────────────────────────────────

@router.get("/dev-users")
def list_dev_users(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Lista todos os usuários Dev. Acesso: apenas dev."""
    users = dev_db.query(models.DevUser).order_by(models.DevUser.created_at.desc()).all()
    return [
        {"id": u.id, "username": u.username, "created_at": u.created_at}
        for u in users
    ]


@router.delete("/dev-users/{user_id}")
def delete_dev_user(
    user_id: int,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Remove um usuário Dev. Não é possível remover o próprio usuário. Acesso: apenas dev."""
    user = dev_db.query(models.DevUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.username == current.sub:
        raise HTTPException(status_code=400, detail="Não é possível remover o próprio usuário")
    dev_db.delete(user)
    dev_db.commit()
    return {"message": f"Usuário '{user.username}' removido"}


# ─── Permissões ARK ───────────────────────────────────────────────────────────

@router.get("/permissions")
def get_permissions(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Retorna os grupos ARK mapeados para role admin. Acesso: apenas dev."""
    cfg = dev_db.query(models.SystemConfig).filter_by(key="admin_groups").first()
    if cfg:
        return {"admin_groups": json.loads(cfg.value)}
    return {"admin_groups": ["admin", "mod", "owner"]}


class _PermissionsRequest(BaseModel):
    admin_groups: list[str]


@router.put("/permissions")
def update_permissions(
    body: _PermissionsRequest,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Atualiza os grupos ARK mapeados para role admin. Acesso: apenas dev."""
    cfg = dev_db.query(models.SystemConfig).filter_by(key="admin_groups").first()
    value = json.dumps(body.admin_groups)
    if cfg:
        cfg.value = value
        cfg.updated_at = datetime.now(timezone.utc)
    else:
        dev_db.add(models.SystemConfig(key="admin_groups", value=value))
    dev_db.commit()
    return {"admin_groups": body.admin_groups}


# ─── Banco de Dados ───────────────────────────────────────────────────────────

@router.get("/database")
def database_stats(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    db: Session = Depends(get_db),
    dev_db: Session = Depends(get_dev_db),
):
    """Contagem de registros por tabela. Acesso: apenas dev."""
    try:
        players = db.query(models.Player).count()
        snapshots = db.query(models.InventorySnapshot).count()
        items = db.query(models.InventoryItem).count()
    except Exception:
        players = snapshots = items = "–"
    return {
        "players": players,
        "inventory_snapshots": snapshots,
        "inventory_items": items,
        "dev_users": dev_db.query(models.DevUser).count(),
        "audit_logs": dev_db.query(models.AuditLog).count(),
    }


class _CleanupRequest(BaseModel):
    days: int


@router.post("/database/cleanup")
def cleanup_database(
    body: _CleanupRequest,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    db: Session = Depends(get_db),
):
    """Remove snapshots mais antigos que N dias (cascata). Acesso: apenas dev."""
    if body.days < 1:
        raise HTTPException(status_code=400, detail="Mínimo de 1 dia")
    cutoff = datetime.now(timezone.utc) - timedelta(days=body.days)
    deleted = (
        db.query(models.InventorySnapshot)
        .filter(models.InventorySnapshot.uploaded_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted_snapshots": deleted, "message": f"{deleted} snapshot(s) removido(s)"}


# ─── Logs de Auditoria ────────────────────────────────────────────────────────

@router.get("/audit")
def audit_logs(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
    limit: int = Query(100, le=500),
):
    """Retorna os últimos eventos de autenticação. Acesso: apenas dev."""
    logs = (
        dev_db.query(models.AuditLog)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "timestamp": log.timestamp,
            "event_type": log.event_type,
            "identifier": log.identifier,
            "ip_address": log.ip_address,
            "role_assigned": log.role_assigned,
            "details": log.details,
        }
        for log in logs
    ]


# ─── Configurações do Sistema ─────────────────────────────────────────────────

_ALLOWED_CONFIG_KEYS = frozenset({"admin_groups", "jwt_expire_minutes", "cors_origins", "steam_return_url"})


@router.get("/config")
def get_config(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Retorna todas as configurações do sistema. Acesso: apenas dev."""
    configs = dev_db.query(models.SystemConfig).all()
    result: dict = {}
    for c in configs:
        try:
            result[c.key] = json.loads(c.value)
        except Exception:
            result[c.key] = c.value
    return result


class _ConfigUpdateRequest(BaseModel):
    value: str


@router.put("/config/{key}")
def update_config(
    key: str,
    body: _ConfigUpdateRequest,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    dev_db: Session = Depends(get_dev_db),
):
    """Atualiza uma chave de configuração do sistema. Acesso: apenas dev."""
    if key not in _ALLOWED_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Chave '{key}' não permitida")
    cfg = dev_db.query(models.SystemConfig).filter_by(key=key).first()
    if cfg:
        cfg.value = body.value
        cfg.updated_at = datetime.now(timezone.utc)
    else:
        dev_db.add(models.SystemConfig(key=key, value=body.value))
    dev_db.commit()
    return {"key": key, "value": body.value}


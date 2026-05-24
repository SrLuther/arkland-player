import json as _json
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src.dev_database import get_dev_db
from src import auth as auth_utils, models

router = APIRouter()

# URL base do Steam OpenID — o return_to é codificado como query param
_STEAM_LOGIN_TEMPLATE = (
    "https://steamcommunity.com/openid/login"
    "?openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
    "&openid.mode=checkid_setup"
    "&openid.return_to={return_to}"
    "&openid.realm={realm}"
    "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
    "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
)


@router.get("/steam/login")
def steam_login(request: Request, local_redirect: Optional[str] = None):
    """
    Inicia o fluxo de login via Steam OpenID 2.0.

    Parâmetro opcional `local_redirect`: URL local (ex: http://localhost:PORT/callback)
    para redirecionar após o login — usado pelo app desktop.
    """
    realm = str(request.base_url).rstrip("/")
    return_to = settings.STEAM_OPENID_RETURN_URL
    if local_redirect:
        sep = "&" if "?" in return_to else "?"
        return_to = f"{return_to}{sep}local_redirect={urllib.parse.quote(local_redirect, safe='')}"

    url = _STEAM_LOGIN_TEMPLATE.format(
        return_to=urllib.parse.quote(return_to, safe=""),
        realm=urllib.parse.quote(realm, safe=""),
    )
    return RedirectResponse(url=url)


@router.get("/steam/callback")
async def steam_callback(
    request: Request,
    local_redirect: Optional[str] = None,
    db: Session = Depends(get_db),
    dev_db: Session = Depends(get_dev_db),
):
    """Callback do Steam OpenID. Valida identidade e emite JWT com role."""
    params = dict(request.query_params)
    clean_params = {k: v for k, v in params.items() if k != "local_redirect"}

    steam_id = await auth_utils.verify_steam_openid(clean_params)
    if not steam_id:
        raise HTTPException(status_code=401, detail="Autenticação Steam falhou")

    persona_name = await auth_utils.get_steam_persona(steam_id)
    player = auth_utils.get_or_create_player(steam_id, persona_name, db)

    # Lê grupos admin do SystemConfig (SQLite local)
    _cfg_row = dev_db.query(models.SystemConfig).filter_by(key="admin_groups").first()
    _admin_groups = frozenset(_json.loads(_cfg_row.value)) if _cfg_row else None
    role = auth_utils.steam_role(player.permission_group, _admin_groups)

    # Auditoria (SQLite local)
    dev_db.add(models.AuditLog(
        event_type="steam_login",
        identifier=steam_id,
        ip_address=request.client.host if request.client else None,
        role_assigned=role,
        details=_json.dumps({"persona_name": persona_name}),
    ))
    dev_db.commit()

    token = auth_utils.create_jwt(player.steam_id, role)

    if local_redirect:
        safe_name = urllib.parse.quote(persona_name, safe="")
        redirect_url = (
            f"{local_redirect}?jwt={token}"
            f"&steam_id={steam_id}"
            f"&persona_name={safe_name}"
            f"&role={role}"
        )
        return RedirectResponse(url=redirect_url)

    return {
        "access_token": token,
        "token_type": "bearer",
        "steam_id": steam_id,
        "persona_name": persona_name,
        "role": role,
    }


# ─── Dev login (legado) ──────────────────────────────────────────────────────

class _DevLoginRequest(BaseModel):
    username: str
    password: str


@router.post("/dev/login")
def dev_login(body: _DevLoginRequest, request: Request, dev_db: Session = Depends(get_dev_db)):
    """Login para usuários DEV — valida contra credenciais fixas no código, sem depender do banco."""
    from src.config import DEV_USERNAME, DEV_PASSWORD
    ip = request.client.host if request.client else None

    # Valida contra as credenciais fixas (constantes de módulo, nunca sobrescritas pelo .env)
    credentials_ok = (
        body.username == DEV_USERNAME
        and body.password == DEV_PASSWORD
    )

    if not credentials_ok:
        dev_db.add(models.AuditLog(
            event_type="dev_login_fail",
            identifier=body.username,
            ip_address=ip,
        ))
        dev_db.commit()
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = auth_utils.create_jwt(body.username, "dev")
    dev_db.add(models.AuditLog(
        event_type="dev_login",
        identifier=body.username,
        ip_address=ip,
        role_assigned="dev",
    ))
    dev_db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "dev",
        "username": body.username,
    }


# ─── Dev elevate (Steam + senha master) ────────────────────────────────────────

class _DevElevateRequest(BaseModel):
    master_password: str


@router.post("/dev/elevate")
def dev_elevate(
    body: _DevElevateRequest,
    current: auth_utils.CurrentUser = Depends(auth_utils.get_current_user),
):
    """Eleva o JWT de um usuário Steam autenticado para role=dev, validando a senha master."""
    if not settings.MASTER_PASSWORD:
        raise HTTPException(status_code=403, detail="Elevação Dev desativada no servidor")
    if body.master_password != settings.MASTER_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha master inválida")
    token = auth_utils.create_jwt(current.sub, "dev")
    return {"access_token": token, "token_type": "bearer", "role": "dev"}

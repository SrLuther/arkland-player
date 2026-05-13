import urllib.parse
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src import auth as auth_utils

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
        # Passa o local_redirect como query param no return_to para recuperar após callback
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
):
    """Callback do Steam OpenID. Valida identidade e emite JWT."""
    params = dict(request.query_params)
    # Remove nosso parâmetro customizado antes de validar com Steam
    clean_params = {k: v for k, v in params.items() if k != "local_redirect"}

    steam_id = await auth_utils.verify_steam_openid(clean_params)
    if not steam_id:
        raise HTTPException(status_code=401, detail="Autenticação Steam falhou")

    persona_name = await auth_utils.get_steam_persona(steam_id)
    player = auth_utils.get_or_create_player(steam_id, persona_name, db)
    token = auth_utils.create_jwt(player.steam_id)

    # Se veio do app desktop, redireciona para o servidor local com o token
    if local_redirect:
        safe_name = urllib.parse.quote(persona_name, safe="")
        redirect_url = f"{local_redirect}?jwt={token}&steam_id={steam_id}&persona_name={safe_name}"
        return RedirectResponse(url=redirect_url)

    # Resposta JSON para uso via API direta
    return {
        "access_token": token,
        "token_type": "bearer",
        "steam_id": steam_id,
        "persona_name": persona_name,
    }

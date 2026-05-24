"""Rotas de gerenciamento do bot Discord.

Permite ao painel Dev controlar o processo do bot (start/stop/restart),
visualizar logs, listar/toggle de cogs e editar a configuração do .env.
"""
import os
import pathlib
import re
import signal
import socket
import subprocess
import sys
import time as _time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src import auth as auth_utils

router = APIRouter()

# Caminho base do bot dentro do projeto
_BOT_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "bot"
_BOT_ENV = _BOT_DIR / ".env"
_BOT_LOG = _BOT_DIR / "bot_output.log"
_BOT_COGS_DIR = _BOT_DIR / "cogs"
_BOT_DISABLED_FILE = _BOT_DIR / ".disabled_cogs"

# Processo em memória (persiste enquanto o backend estiver no ar)
_bot_process: Optional[subprocess.Popen] = None
_bot_start_time: Optional[float] = None


# ─── Utilitários internos ─────────────────────────────────────────────────────

def _is_running() -> bool:
    global _bot_process
    if _bot_process is None:
        return False
    return _bot_process.poll() is None


def _load_disabled_cogs() -> set[str]:
    if not _BOT_DISABLED_FILE.exists():
        return set()
    return set(_BOT_DISABLED_FILE.read_text(encoding="utf-8").splitlines())


def _save_disabled_cogs(disabled: set[str]) -> None:
    _BOT_DISABLED_FILE.write_text("\n".join(sorted(disabled)), encoding="utf-8")


# ─── Status ───────────────────────────────────────────────────────────────────

@router.get("/status")
def bot_status(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Status atual do processo do bot."""
    running = _is_running()
    uptime = round(_time.time() - _bot_start_time, 1) if running and _bot_start_time else None
    pid = _bot_process.pid if running and _bot_process else None
    return {
        "running": running,
        "pid": pid,
        "uptime_seconds": uptime,
        "hostname": socket.gethostname(),
        "bot_dir": str(_BOT_DIR),
    }


# ─── Controle de processo ─────────────────────────────────────────────────────

@router.post("/start")
def bot_start(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Inicia o bot Discord."""
    global _bot_process, _bot_start_time
    if _is_running():
        raise HTTPException(status_code=409, detail="Bot já está em execução")
    if not (_BOT_DIR / "bot.py").exists():
        raise HTTPException(status_code=500, detail="bot.py não encontrado")

    log_file = open(_BOT_LOG, "a", encoding="utf-8")

    # Prefere o venv local do bot, depois uv run, por último sys.executable
    _venv_python = (
        _BOT_DIR / ".venv" / ("Scripts\\python.exe" if sys.platform == "win32" else "bin/python")
    )
    if _venv_python.exists():
        python_cmd = [str(_venv_python), "bot.py"]
    else:
        import shutil
        uv = shutil.which("uv")
        python_cmd = [uv, "run", "bot.py"] if uv else [sys.executable, "bot.py"]

    _bot_process = subprocess.Popen(
        python_cmd,
        cwd=str(_BOT_DIR),
        stdout=log_file,
        stderr=log_file,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    _bot_start_time = _time.time()
    return {"message": "Bot iniciado", "pid": _bot_process.pid}


@router.post("/stop")
def bot_stop(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Para o bot Discord."""
    global _bot_process, _bot_start_time
    if not _is_running():
        raise HTTPException(status_code=409, detail="Bot não está em execução")
    try:
        if sys.platform == "win32":
            _bot_process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            _bot_process.terminate()
        _bot_process.wait(timeout=10)
    except Exception:
        _bot_process.kill()
    _bot_process = None
    _bot_start_time = None
    return {"message": "Bot encerrado"}


@router.post("/restart")
def bot_restart(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Reinicia o bot Discord."""
    if _is_running():
        bot_stop(current)
    return bot_start(current)


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
def bot_logs(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
    lines: int = Query(100, le=500),
):
    """Retorna as últimas N linhas do log do bot."""
    if not _BOT_LOG.exists():
        return {"lines": []}
    content = _BOT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": content[-lines:]}


@router.delete("/logs")
def clear_bot_logs(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Limpa o arquivo de log do bot."""
    if _BOT_LOG.exists():
        _BOT_LOG.write_text("", encoding="utf-8")
    return {"message": "Log limpo"}


# ─── Cogs ─────────────────────────────────────────────────────────────────────

@router.get("/cogs")
def list_cogs(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Lista todos os cogs e seu estado (ativo/desativado)."""
    if not _BOT_COGS_DIR.exists():
        return []
    disabled = _load_disabled_cogs()
    cogs = []
    for f in sorted(_BOT_COGS_DIR.glob("*.py")):
        if f.stem.startswith("_"):
            continue
        cogs.append({"name": f.stem, "enabled": f.stem not in disabled})
    return cogs


class _CogToggleRequest(BaseModel):
    enabled: bool


@router.put("/cogs/{name}")
def toggle_cog(
    name: str,
    body: _CogToggleRequest,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Ativa ou desativa um cog (requer restart do bot para ter efeito)."""
    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        raise HTTPException(status_code=400, detail="Nome de cog inválido")
    cog_file = _BOT_COGS_DIR / f"{name}.py"
    if not cog_file.exists():
        raise HTTPException(status_code=404, detail="Cog não encontrado")
    disabled = _load_disabled_cogs()
    if body.enabled:
        disabled.discard(name)
    else:
        disabled.add(name)
    _save_disabled_cogs(disabled)
    return {"name": name, "enabled": body.enabled}


# ─── Configuração (.env do bot) ───────────────────────────────────────────────

@router.get("/config")
def get_bot_config(
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Retorna as configurações do .env do bot (sem valores de secrets mascarados)."""
    if not _BOT_ENV.exists():
        return {}
    config: dict[str, str] = {}
    for line in _BOT_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()
    return config


class _BotConfigUpdate(BaseModel):
    config: dict[str, str]


@router.put("/config")
def update_bot_config(
    body: _BotConfigUpdate,
    current: auth_utils.CurrentUser = Depends(auth_utils.require_role("dev")),
):
    """Atualiza chaves no .env do bot. Preserva comentários e ordem."""
    if not _BOT_ENV.exists():
        raise HTTPException(status_code=404, detail=".env do bot não encontrado")

    lines = _BOT_ENV.read_text(encoding="utf-8").splitlines()
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in body.config:
                new_lines.append(f"{key}={body.config[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Adiciona chaves novas que não existiam
    for key, value in body.config.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    _BOT_ENV.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return {"updated": list(body.config.keys())}

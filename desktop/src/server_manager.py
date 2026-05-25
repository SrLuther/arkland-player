"""Gerencia o processo do servidor backend (FastAPI/uvicorn)."""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
from typing import Optional


def get_local_ip() -> str:
    """Retorna o IP local da máquina na LAN (não localhost)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _app_dir() -> pathlib.Path:
    """Diretório raiz do executável (ou do script em modo dev)."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    # dev: desktop/src/server_manager.py → sobe dois níveis até desktop/
    return pathlib.Path(__file__).parent.parent


def _find_server() -> Optional[pathlib.Path]:
    """
    Localiza o backend:
      - Frozen: ArklandPlayer-Server.exe na mesma pasta que o exe
      - Dev:    ../../backend/main.py relativo a desktop/
    """
    if getattr(sys, "frozen", False):
        root = _app_dir()
        for name in ("ArklandPlayer-Server.exe", "server.exe"):
            p = root / name
            if p.exists():
                return p
        return None
    else:
        p = _app_dir().parent / "backend" / "main.py"
        return p if p.exists() else None


def _find_uv() -> str:
    """Retorna o caminho do executável uv."""
    for candidate in (
        pathlib.Path.home() / ".local" / "bin" / "uv.exe",
        pathlib.Path.home() / ".local" / "bin" / "uv",
    ):
        if candidate.exists():
            return str(candidate)
    return "uv"  # assume PATH


class ServerManager:
    """Ciclo de vida do processo do backend."""

    PORT = 5000

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None

    # ── estado ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def local_ip(self) -> str:
        return get_local_ip()

    @property
    def url(self) -> str:
        return f"http://{self.local_ip}:{self.PORT}"

    # ── controle ──────────────────────────────────────────────────────────

    def start(self) -> tuple[bool, str]:
        """
        Inicia o backend.
        Retorna (True, url) em caso de sucesso ou (False, mensagem_de_erro).
        """
        if self.is_running:
            return True, self.url

        server = _find_server()
        if server is None:
            return False, "Arquivo do servidor não encontrado."

        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

            if getattr(sys, "frozen", False):
                # Frozen: executa ArklandPlayer-Server.exe diretamente
                cmd = [str(server)]
                cwd = None
            else:
                # Dev: uv run main.py dentro do diretório backend/
                uv = _find_uv()
                cmd = [uv, "run", "main.py"]
                cwd = str(server.parent)

            self._proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, self.url

        except Exception as exc:
            return False, f"Erro ao iniciar servidor: {exc}"

    def stop(self) -> None:
        """Encerra o processo do backend."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

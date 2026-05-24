"""
Verificador de atualizações do ARKLAND Player via GitHub Releases API.

Formato da release no GitHub:
    Tag: v1.2.3
    A API retorna: {"tag_name": "v1.2.3", "body": "...", "assets": [...]}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

_GITHUB_API = "https://api.github.com/repos/SrLuther/arkland-player/releases/latest"

# Localiza o VERSION a partir do diretório do projeto
_PROJECT_ROOT = Path(__file__).parent.parent.parent  # arkland-player/
_VERSION_FILE = _PROJECT_ROOT / "VERSION"


def _read_local_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip().lstrip("v")
    except Exception:
        return "0.0.0"


def _parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


@dataclass
class UpdateInfo:
    version: str          # ex: "1.2.3"
    tag: str              # ex: "v1.2.3"
    changelog: str        # corpo da release note

    def is_newer_than(self, current: str) -> bool:
        return _parse_version(self.version) > _parse_version(current)


class UpdateChecker:
    def __init__(
        self,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_log = on_log or (lambda msg: None)
        self._latest: Optional[UpdateInfo] = None
        self._checking = False

    @property
    def latest(self) -> Optional[UpdateInfo]:
        return self._latest

    @property
    def current_version(self) -> str:
        return _read_local_version()

    def check_async(
        self,
        on_result: Optional[Callable[[Optional[UpdateInfo]], None]] = None,
    ) -> None:
        if self._checking:
            return
        threading.Thread(
            target=self._worker,
            args=(on_result,),
            daemon=True,
            name="ArkPlayerUpdateChecker",
        ).start()

    def _worker(
        self,
        on_result: Optional[Callable[[Optional[UpdateInfo]], None]],
    ) -> None:
        self._checking = True
        result: Optional[UpdateInfo] = None
        try:
            result = self._fetch()
            self._latest = result
        except Exception as exc:
            self._on_log(f"[update] Erro ao verificar: {exc}")
        finally:
            self._checking = False
            if on_result:
                on_result(result)

    def _fetch(self) -> UpdateInfo:
        try:
            import requests as _req
        except ImportError:
            from urllib.request import urlopen
            import json as _json
            with urlopen(_GITHUB_API, timeout=8) as resp:
                data = _json.loads(resp.read())
        else:
            resp = _req.get(_GITHUB_API, timeout=8, headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            data = resp.json()

        tag = str(data.get("tag_name", ""))
        version = tag.lstrip("v") or str(data.get("name", ""))
        changelog = str(data.get("body", ""))
        return UpdateInfo(version=version, tag=tag, changelog=changelog)

    def launch_updater(self) -> None:
        """Lança o agente de atualização e fecha o app principal."""
        import os

        pid = os.getpid()
        # Localiza o desktop/ como diretório do projeto do desktop
        app_dir = Path(__file__).parent.parent   # arkland-player/desktop/
        script = str(app_dir / "main.py")
        agent = app_dir / "updater_agent.py"

        if not agent.exists():
            raise FileNotFoundError(f"updater_agent.py não encontrado em {agent}")

        # Usa uv se disponível, senão sys.executable
        import shutil
        uv = shutil.which("uv")
        if uv:
            cmd = [uv, "run", str(agent), "--pid", str(pid), "--app-dir", str(_PROJECT_ROOT), "--script", script]
        else:
            cmd = [sys.executable, str(agent), "--pid", str(pid), "--app-dir", str(_PROJECT_ROOT), "--script", script]

        _CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | _CREATE_BREAKAWAY_FROM_JOB
        ) if sys.platform == "win32" else 0

        subprocess.Popen(
            cmd,
            cwd=str(app_dir),
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

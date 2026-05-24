"""
ARKLAND Player — Agente de Atualização

Lançado automaticamente pelo app quando uma nova versão é detectada.
Este processo:
  1. Aguarda o app principal fechar (via PID)
  2. Encerra quaisquer instâncias restantes pelo título da janela
  3. Executa `git pull` no repositório
  4. Reinicia o app via `uv run main.py`
  5. Fecha sozinho

Uso:
    python updater_agent.py --pid <pid> --app-dir <path> --script <path>
    uv run updater_agent.py --pid <pid> --app-dir <path> --script <path>
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import customtkinter as ctk
    _CTK = True
except ImportError:
    import tkinter as ctk  # type: ignore[no-redef]
    _CTK = False

# ── Paleta ────────────────────────────────────────────────────────────────────
_BG      = "#111118"
_CARD_BG = "#1e1e30"
_GREEN   = "#00b09b"
_TEXT    = "#e0e0f0"


class UpdaterApp:
    def __init__(self, pid: int, app_dir: str, script: str, zip_url: str = "") -> None:
        self._pid     = pid
        self._app_dir = Path(app_dir)
        self._script  = script
        self._zip_url = zip_url  # Se preenchido: download zip (modo exe)

        if _CTK:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self._root = ctk.CTk()
        else:
            import tkinter as tk
            self._root = tk.Tk()

        self._root.title("ARKLAND Player — Atualizando")
        self._root.geometry("500x220")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._noop)

        # Centraliza
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"500x220+{(sw - 500) // 2}+{(sh - 220) // 2}")

        self._build_ui()
        self._root.after(400, self._start_worker)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        if not _CTK:
            return

        outer = ctk.CTkFrame(self._root, fg_color=_BG)
        outer.pack(fill="both", expand=True)

        card = ctk.CTkFrame(outer, fg_color=_CARD_BG, corner_radius=12)
        card.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            card,
            text="Atualizando ARKLAND Player...",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_TEXT,
        ).pack(pady=(18, 6))

        self._status_lbl = ctk.CTkLabel(
            card, text="Iniciando...",
            text_color="gray70",
            font=ctk.CTkFont(size=12),
        )
        self._status_lbl.pack(pady=(0, 10))

        self._progress = ctk.CTkProgressBar(card, width=420, height=14, corner_radius=6)
        self._progress.pack(pady=(0, 6))
        self._progress.set(0)

        self._detail_lbl = ctk.CTkLabel(
            card, text="",
            text_color="gray50",
            font=ctk.CTkFont(size=11),
        )
        self._detail_lbl.pack()

    def _set_status(self, text: str, detail: str = "") -> None:
        def _apply() -> None:
            if _CTK:
                self._status_lbl.configure(text=text)
                self._detail_lbl.configure(text=detail)
        self._root.after(0, _apply)

    def _set_progress(self, pct: float) -> None:
        def _apply() -> None:
            if _CTK:
                self._progress.set(max(0.0, min(1.0, pct)))
        self._root.after(0, _apply)

    def _noop(self) -> None:
        pass

    # ── Worker ────────────────────────────────────────────────────────────────

    def _start_worker(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="UpdaterWorker").start()

    def _run(self) -> None:
        try:
            # 1. Aguarda o app principal fechar
            self._set_status("Aguardando o app fechar...")
            self._set_progress(0.05)
            self._wait_pid(self._pid)
            time.sleep(0.5)

            # 2. Mata instâncias restantes
            self._set_status("Encerrando processos restantes...")
            self._kill_lingering()
            self._set_progress(0.15)
            time.sleep(0.3)

            # 3. Atualização
            if self._zip_url:
                self._set_status("Baixando atualização...", self._zip_url)
                self._set_progress(0.30)
                self._zip_update()
            else:
                self._set_status("Baixando atualização...", "git pull origin main")
                self._set_progress(0.30)
                self._git_pull()
            self._set_progress(0.80)

            # 4. Reiniciar app
            self._set_status("Atualização concluída!", "Iniciando ARKLAND Player...")
            self._set_progress(1.0)
            time.sleep(1.2)
            self._relaunch()

            self._root.after(500, self._root.destroy)

        except Exception as exc:
            self._set_status(f"Erro: {exc}", "Feche esta janela manualmente.")
            self._root.after(
                0,
                lambda: self._root.protocol("WM_DELETE_WINDOW", self._root.destroy),
            )

    def _wait_pid(self, pid: int) -> None:
        """Aguarda o processo terminar via WinAPI (sem polling ativo)."""
        SYNCHRONIZE = 0x00100000
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if handle:
                kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                kernel32.WaitForSingleObject(handle, 25_000)
                kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel32.CloseHandle(handle)
                return
        except Exception:
            pass
        # Fallback: polling
        while True:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.5)

    def _kill_lingering(self) -> None:
        """Mata processos com título de janela 'ARKLAND Player'."""
        try:
            subprocess.run(
                ["taskkill", "/F", "/FI", "WINDOWTITLE eq ARKLAND Player*"],
                capture_output=True,
            )
        except Exception:
            pass
        # Aguarda até 8 s para confirmar
        for _ in range(8):
            time.sleep(1)
            result = subprocess.run(
                ["tasklist", "/FI", "WINDOWTITLE eq ARKLAND Player*", "/NH"],
                capture_output=True, text=True,
            )
            if "main.py" not in result.stdout.lower() and "python" not in result.stdout.lower():
                break

    def _zip_update(self) -> None:
        """Modo exe: baixa o zip da release e extrai sobre o diretório instalado."""
        import tempfile, zipfile, shutil, urllib.request

        tmp = Path(tempfile.mkdtemp(prefix="arkland_upd_"))
        zip_path = tmp / "update.zip"

        # Download
        self._set_status("Baixando...", "Aguarde")
        urllib.request.urlretrieve(self._zip_url, zip_path)

        # Extrai
        self._set_status("Extraindo arquivos...")
        extracted = tmp / "out"
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extracted)

        # Se tiver pasta raiz única, entra nela
        items = list(extracted.iterdir())
        if len(items) == 1 and items[0].is_dir():
            extracted = items[0]

        # Copia sobre o diretório do app
        self._set_status("Instalando...")
        shutil.copytree(str(extracted), str(self._app_dir), dirs_exist_ok=True)

        # Limpeza
        shutil.rmtree(tmp, ignore_errors=True)

    def _git_pull(self) -> None:
        """Atualiza o repositório local com git fetch + reset --hard."""
        import shutil
        git = shutil.which("git")
        if not git:
            raise RuntimeError("git não encontrado no PATH.")

        # Garante que estamos na branch principal
        subprocess.run(
            [git, "fetch", "origin"],
            cwd=str(self._app_dir),
            check=True,
            capture_output=True,
            timeout=60,
        )
        subprocess.run(
            [git, "reset", "--hard", "origin/main"],
            cwd=str(self._app_dir),
            check=True,
            capture_output=True,
            timeout=30,
        )

    def _relaunch(self) -> None:
        """Reinicia o app: chama o .exe diretamente (frozen) ou uv run main.py (dev)."""
        script = Path(self._script)

        if script.suffix.lower() == ".exe":
            # Modo frozen: relança o próprio exe
            cmd = [str(script)]
            cwd = str(script.parent)
        else:
            # Modo dev: uv run main.py ou python main.py
            import shutil
            uv = shutil.which("uv")
            cmd = [uv, "run", "main.py"] if uv else [sys.executable, "main.py"]
            cwd = str(script.parent)

        subprocess.Popen(
            cmd,
            cwd=cwd,
            creationflags=(
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            ) if sys.platform == "win32" else 0,
            close_fds=True,
        )

    def run(self) -> None:
        self._root.mainloop()


# ── Entry-point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ARKLAND Player Updater Agent")
    parser.add_argument("--pid",     required=True,  type=int, help="PID do app principal")
    parser.add_argument("--app-dir", required=True,  help="Diretório de instalação do app")
    parser.add_argument("--script",  required=True,  help="Caminho para desktop/main.py ou ArklandPlayer.exe")
    parser.add_argument("--zip-url", default="",     help="URL do .zip da release (modo exe)")
    args = parser.parse_args()

    agent = UpdaterApp(
        pid=args.pid,
        app_dir=args.app_dir,
        script=args.script,
        zip_url=args.zip_url,
    )
    agent.run()


if __name__ == "__main__":
    main()

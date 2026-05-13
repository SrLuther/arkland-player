import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional

_LOCAL_PORT = 15743


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captura o callback do Steam/backend com o JWT."""

    callback: Optional[Callable] = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        jwt   = params.get("jwt",          [""])[0]
        sid   = params.get("steam_id",     [""])[0]
        name  = params.get("persona_name", [""])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            b"<html><body style='font-family:sans-serif;background:#161622;color:#fff;"
            b"display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
            b"<h2>Login realizado com sucesso!<br>Pode fechar esta aba.</h2></body></html>"
        )
        self.wfile.write(html)

        if _CallbackHandler.callback and jwt:
            _CallbackHandler.callback(jwt, sid, urllib.parse.unquote(name))

    def log_message(self, *args):
        pass  # silencia logs do servidor HTTP local


def start_steam_login(
    backend_url: str,
    on_success: Callable[[str, str, str], None],
) -> None:
    """
    Abre o navegador para o login Steam e aguarda o callback numa thread.
    `on_success(jwt, steam_id, persona_name)` é chamado na thread do servidor.
    """
    _CallbackHandler.callback = on_success

    local_redirect = urllib.parse.quote(
        f"http://127.0.0.1:{_LOCAL_PORT}/callback", safe=""
    )
    login_url = f"{backend_url.rstrip('/')}/auth/steam/login?local_redirect={local_redirect}"

    def _serve():
        server = HTTPServer(("127.0.0.1", _LOCAL_PORT), _CallbackHandler)
        server.timeout = 180  # aguarda até 3 minutos
        server.handle_request()
        server.server_close()

    threading.Thread(target=_serve, daemon=True).start()
    webbrowser.open(login_url)

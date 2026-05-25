import requests
from typing import Optional


class ApiClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get_me(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/player/me", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def get_snapshots(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/player/me/snapshots", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def get_snapshot_items(self, snapshot_id: int) -> list:
        try:
            r = requests.get(
                f"{self.base_url}/player/me/snapshots/{snapshot_id}/items",
                headers=self._headers(), timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def dev_login(self, username: str, password: str) -> "tuple[Optional[dict], str]":
        """Retorna (data, erro). data é dict em sucesso, None em falha. erro é string vazia em sucesso."""
        try:
            r = requests.post(
                f"{self.base_url}/auth/dev/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json(), ""
            if r.status_code == 401:
                return None, "Credenciais inválidas."
            return None, f"Erro do servidor: {r.status_code}"
        except requests.exceptions.ConnectionError:
            return None, "Sem conexão com o backend. Verifique a URL."
        except requests.exceptions.Timeout:
            return None, "Backend não respondeu (timeout)."
        except Exception as e:
            return None, f"Erro: {e}"

    def dev_elevate(self, master_password: str) -> Optional[dict]:
        """Eleva JWT Steam para role=dev validando a senha master. Retorna {access_token, role} ou None."""
        try:
            r = requests.post(
                f"{self.base_url}/auth/dev/elevate",
                json={"master_password": master_password},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def get_all_players(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/admin/players", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def get_stats(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/admin/stats", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def create_dev_user(self, username: str, password: str) -> Optional[dict]:
        try:
            r = requests.post(
                f"{self.base_url}/admin/dev-users",
                json={"username": username, "password": password},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ─── Dev: Health / Status ─────────────────────────────────────────────────

    def get_health_status(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/admin/health", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ─── Dev: Usuários Dev ────────────────────────────────────────────────────

    def get_dev_users(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/admin/dev-users", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def delete_dev_user(self, user_id: int) -> bool:
        try:
            r = requests.delete(
                f"{self.base_url}/admin/dev-users/{user_id}",
                headers=self._headers(),
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    # ─── Dev: Permissões ARK ──────────────────────────────────────────────────

    def get_permissions(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/admin/permissions", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def update_permissions(self, admin_groups: list) -> Optional[dict]:
        try:
            r = requests.put(
                f"{self.base_url}/admin/permissions",
                json={"admin_groups": admin_groups},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ─── Dev: Banco de Dados ──────────────────────────────────────────────────

    def get_database_stats(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/admin/database", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def cleanup_database(self, days: int) -> Optional[dict]:
        try:
            r = requests.post(
                f"{self.base_url}/admin/database/cleanup",
                json={"days": days},
                headers=self._headers(),
                timeout=30,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ─── Dev: Logs de Auditoria ───────────────────────────────────────────────

    def get_audit_logs(self, limit: int = 100) -> list:
        try:
            r = requests.get(
                f"{self.base_url}/admin/audit",
                params={"limit": limit},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    # ─── Dev: Configurações do Backend ───────────────────────────────────────

    def get_backend_config(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/admin/config", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def update_backend_config(self, key: str, value: str) -> Optional[dict]:
        try:
            r = requests.put(
                f"{self.base_url}/admin/config/{key}",
                json={"value": value},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ─── Bot Discord ──────────────────────────────────────────────────────────

    def get_bot_status(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/bot/status", headers=self._headers(), timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def bot_start(self) -> Optional[dict]:
        try:
            r = requests.post(f"{self.base_url}/bot/start", headers=self._headers(), timeout=10)
            return r.json()
        except Exception:
            pass
        return None

    def bot_stop(self) -> Optional[dict]:
        try:
            r = requests.post(f"{self.base_url}/bot/stop", headers=self._headers(), timeout=15)
            return r.json()
        except Exception:
            pass
        return None

    def bot_restart(self) -> Optional[dict]:
        try:
            r = requests.post(f"{self.base_url}/bot/restart", headers=self._headers(), timeout=20)
            return r.json()
        except Exception:
            pass
        return None

    def get_bot_logs(self, lines: int = 100) -> list:
        try:
            r = requests.get(
                f"{self.base_url}/bot/logs",
                params={"lines": lines},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("lines", [])
        except Exception:
            pass
        return []

    def clear_bot_logs(self) -> bool:
        try:
            r = requests.delete(f"{self.base_url}/bot/logs", headers=self._headers(), timeout=8)
            return r.status_code == 200
        except Exception:
            pass
        return False

    def get_bot_cogs(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/bot/cogs", headers=self._headers(), timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def toggle_bot_cog(self, name: str, enabled: bool) -> Optional[dict]:
        try:
            r = requests.put(
                f"{self.base_url}/bot/cogs/{name}",
                json={"enabled": enabled},
                headers=self._headers(),
                timeout=8,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def get_bot_config(self) -> Optional[dict]:
        try:
            r = requests.get(f"{self.base_url}/bot/config", headers=self._headers(), timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def update_bot_config(self, config: dict) -> Optional[dict]:
        try:
            r = requests.put(
                f"{self.base_url}/bot/config",
                json={"config": config},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None


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

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PlayerConfig:
    backend_url: str = "http://localhost:5000"
    jwt_token: str = ""
    steam_id: str = ""
    persona_name: str = ""
    role: str = "player"       # "player" | "admin" | "dev"
    display_name: str = ""    # persona_name (Steam) ou username (Dev)


class ConfigManager:
    def __init__(self) -> None:
        self._config_dir = Path(os.environ.get("APPDATA", "~")) / "ARKLAND-Player"
        self._config_file = self._config_dir / "config.json"
        self.config = PlayerConfig()

    def load(self) -> None:
        try:
            if self._config_file.exists():
                with open(self._config_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                valid = PlayerConfig.__dataclass_fields__.keys()
                self.config = PlayerConfig(**{k: v for k, v in data.items() if k in valid})
        except Exception:
            self.config = PlayerConfig()

    def save(self) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._config_file, "w", encoding="utf-8") as fh:
            json.dump(self.config.__dict__, fh, indent=2, ensure_ascii=False)

    def clear_session(self) -> None:
        self.config.jwt_token = ""
        self.config.steam_id = ""
        self.config.persona_name = ""
        self.config.role = "player"
        self.config.display_name = ""
        self.save()

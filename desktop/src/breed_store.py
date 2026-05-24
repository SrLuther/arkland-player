import json
import uuid
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

STAT_KEYS = ["hp", "stam", "o2", "food", "weight", "melee", "speed"]
STAT_LABELS = {
    "hp":     "HP",
    "stam":   "Stamina",
    "o2":     "Oxigênio",
    "food":   "Comida",
    "weight": "Peso",
    "melee":  "Dano",
    "speed":  "Velocidade",
}
# Incremento padrão por ponto (wild e dom) como fração do base
STAT_DEFAULTS = {
    "hp":     (0.20, 0.20),
    "stam":   (0.10, 0.10),
    "o2":     (0.10, 0.10),
    "food":   (0.15, 0.15),
    "weight": (0.04, 0.04),
    "melee":  (0.05, 0.05),
    "speed":  (0.01, 0.01),
}


@dataclass
class Dino:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    species: str = ""
    gender: str = "Macho"
    level: int = 0
    hp: int = 0
    stam: int = 0
    o2: int = 0
    food: int = 0
    weight: int = 0
    melee: int = 0
    speed: int = 0
    notes: str = ""


class BreedStore:
    def __init__(self) -> None:
        self._dir = Path(os.environ.get("APPDATA", "~")) / "ARKLAND-Player"
        self._file = self._dir / "dinos.json"
        self.dinos: list[Dino] = []

    def load(self) -> None:
        try:
            if self._file.exists():
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid = set(Dino.__dataclass_fields__.keys())
                self.dinos = [
                    Dino(**{k: v for k, v in d.items() if k in valid})
                    for d in data
                ]
        except Exception:
            self.dinos = []

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump([asdict(d) for d in self.dinos], f, indent=2, ensure_ascii=False)

    def add(self, dino: Dino) -> None:
        self.dinos.append(dino)
        self.save()

    def remove(self, dino_id: str) -> None:
        self.dinos = [d for d in self.dinos if d.id != dino_id]
        self.save()

    def best_offspring(self, male_id: str, female_id: str) -> dict:
        male = next((d for d in self.dinos if d.id == male_id), None)
        female = next((d for d in self.dinos if d.id == female_id), None)
        if not male or not female:
            return {}
        return {s: max(getattr(male, s, 0), getattr(female, s, 0)) for s in STAT_KEYS}

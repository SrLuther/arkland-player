from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src import models

router = APIRouter()

# Grupos que têm permissão para usar /u e /dow
# Deve espelhar a configuração do PermissionsManager no servidor ARK
_ALLOWED_GROUPS = {"admin", "mod", "vip", "player"}


# --- Schemas ---

class ItemIn(BaseModel):
    blueprint_path: str
    quantity: int = 1
    quality: float = 0.0
    durability: float = 0.0
    custom_name: Optional[str] = None
    is_equipped: bool = False
    slot_index: int = -1


class UploadPayload(BaseModel):
    steam_id: str
    server_name: str
    map_name: str
    items: List[ItemIn]


class ItemOut(BaseModel):
    blueprint_path: str
    quantity: int
    quality: float
    durability: float
    custom_name: Optional[str]
    is_equipped: bool
    slot_index: int

    model_config = {"from_attributes": True}


# --- Dependência de autenticação do servidor ---

def _require_server_key(x_server_key: str = Header(...)):
    if x_server_key != settings.SERVER_API_KEY:
        raise HTTPException(status_code=403, detail="Chave de servidor inválida")


# --- Endpoints ---

@router.post("/upload", dependencies=[Depends(_require_server_key)])
def upload_inventory(payload: UploadPayload, db: Session = Depends(get_db)):
    """
    Chamado pelo plugin quando o jogador usa /u no servidor ARK.
    Salva o inventário atual como um novo snapshot.
    """
    player = db.query(models.Player).filter_by(steam_id=payload.steam_id).first()
    if not player:
        raise HTTPException(
            status_code=404,
            detail="Jogador não encontrado. Faça login no app ARKLAND Player primeiro.",
        )
    if player.permission_group not in _ALLOWED_GROUPS:
        raise HTTPException(
            status_code=403,
            detail=f"Grupo '{player.permission_group}' não tem permissão para usar /u",
        )

    snapshot = models.InventorySnapshot(
        player_id=player.id,
        server_name=payload.server_name,
        map_name=payload.map_name,
    )
    db.add(snapshot)
    db.flush()

    for item_data in payload.items:
        db.add(models.InventoryItem(snapshot_id=snapshot.id, **item_data.model_dump()))

    db.commit()
    return {
        "message": "Inventário salvo com sucesso",
        "snapshot_id": snapshot.id,
        "items_count": len(payload.items),
    }


@router.get("/download/{steam_id}", response_model=List[ItemOut], dependencies=[Depends(_require_server_key)])
def download_inventory(steam_id: str, db: Session = Depends(get_db)):
    """
    Chamado pelo plugin quando o jogador usa /dow no servidor ARK.
    Retorna os itens do snapshot mais recente.
    """
    player = db.query(models.Player).filter_by(steam_id=steam_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")
    if player.permission_group not in _ALLOWED_GROUPS:
        raise HTTPException(
            status_code=403,
            detail=f"Grupo '{player.permission_group}' não tem permissão para usar /dow",
        )

    snapshot = (
        db.query(models.InventorySnapshot)
        .filter_by(player_id=player.id)
        .order_by(models.InventorySnapshot.uploaded_at.desc())
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Nenhum inventário salvo encontrado")

    return snapshot.items

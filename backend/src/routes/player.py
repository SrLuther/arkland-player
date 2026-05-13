from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src import models
from src.auth import get_current_player

router = APIRouter()


class PlayerOut(BaseModel):
    steam_id: str
    persona_name: Optional[str]
    permission_group: str
    last_seen: datetime

    model_config = {"from_attributes": True}


class SnapshotOut(BaseModel):
    id: int
    server_name: Optional[str]
    map_name: Optional[str]
    uploaded_at: datetime
    items_count: int


@router.get("/me", response_model=PlayerOut)
def get_me(player: models.Player = Depends(get_current_player)):
    """Retorna os dados do jogador autenticado."""
    return player


@router.get("/me/snapshots", response_model=List[SnapshotOut])
def get_snapshots(
    player: models.Player = Depends(get_current_player),
    db: Session = Depends(get_db),
):
    """Retorna os últimos 20 snapshots do jogador."""
    snapshots = (
        db.query(models.InventorySnapshot)
        .filter_by(player_id=player.id)
        .order_by(models.InventorySnapshot.uploaded_at.desc())
        .limit(20)
        .all()
    )
    return [
        SnapshotOut(
            id=s.id,
            server_name=s.server_name,
            map_name=s.map_name,
            uploaded_at=s.uploaded_at,
            items_count=len(s.items),
        )
        for s in snapshots
    ]


@router.get("/me/snapshots/{snapshot_id}/items")
def get_snapshot_items(
    snapshot_id: int,
    player: models.Player = Depends(get_current_player),
    db: Session = Depends(get_db),
):
    """Retorna os itens de um snapshot específico do jogador."""
    snapshot = (
        db.query(models.InventorySnapshot)
        .filter_by(id=snapshot_id, player_id=player.id)
        .first()
    )
    if not snapshot:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Snapshot não encontrado")
    return snapshot.items

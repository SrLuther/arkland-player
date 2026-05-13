from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import relationship

from src.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    steam_id = Column(String(20), unique=True, nullable=False, index=True)
    persona_name = Column(String(255))
    # Grupo de permissão reflete o grupo do PermissionsManager do servidor
    permission_group = Column(String(100), default="player", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    snapshots = relationship("InventorySnapshot", back_populates="player")


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    server_name = Column(String(255))
    map_name = Column(String(255))
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player", back_populates="snapshots")
    items = relationship(
        "InventoryItem",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("inventory_snapshots.id", ondelete="CASCADE"), nullable=False)
    blueprint_path = Column(Text, nullable=False)
    quantity = Column(Integer, default=1)
    quality = Column(Float, default=0.0)
    durability = Column(Float, default=0.0)
    custom_name = Column(String(255), nullable=True)
    is_equipped = Column(Boolean, default=False)
    slot_index = Column(Integer, default=-1)

    snapshot = relationship("InventorySnapshot", back_populates="items")

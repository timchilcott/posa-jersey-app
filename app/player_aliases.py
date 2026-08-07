"""Helpers for matching merged player names during imports."""
import re
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models import Player, PlayerAlias


def normalize_player_alias(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").lower())
    return " ".join(cleaned.split())


def find_player_by_alias(db: Session, name: str) -> Optional[Player]:
    normalized = normalize_player_alias(name)
    if not normalized:
        return None

    alias = db.query(PlayerAlias).options(joinedload(PlayerAlias.player)).filter(
        PlayerAlias.normalized_alias == normalized
    ).first()
    return alias.player if alias else None


def upsert_player_alias(db: Session, player_id: int, alias_name: str) -> Optional[PlayerAlias]:
    normalized = normalize_player_alias(alias_name)
    if not normalized:
        return None

    alias = db.query(PlayerAlias).filter(
        PlayerAlias.normalized_alias == normalized
    ).first()
    if alias:
        alias.player_id = player_id
        alias.alias_name = alias_name
        return alias

    alias = PlayerAlias(
        player_id=player_id,
        alias_name=alias_name,
        normalized_alias=normalized,
    )
    db.add(alias)
    return alias

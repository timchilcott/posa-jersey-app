"""Admin routes for merging duplicate player records."""
import re
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Player, Registration
from app.player_dates import date_of_birth_iso

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _norm(value):
    return (value or "").strip().lower()


def _is_blankish(value):
    return _norm(value) in {"", "unknown", "n/a", "na", "none"}


def _season_year(reg):
    m = re.search(r"20\d{2}", reg.season or "")
    if m:
        return int(m.group())
    return reg.created_at.year if reg.created_at else None


def _registration_key(reg):
    return (_norm(reg.sport), _norm(reg.season))


def _copy_if_missing(target, source, attr, blank_values=None):
    incoming = getattr(source, attr)
    if _is_blankish(incoming):
        return False

    current = getattr(target, attr)
    extra_blank_values = blank_values or set()
    if _is_blankish(current) or _norm(current) in extra_blank_values:
        setattr(target, attr, incoming)
        return True
    return False


def _merge_registration(existing, duplicate):
    if duplicate.confirmation_sent and not existing.confirmation_sent:
        existing.confirmation_sent = True

    _copy_if_missing(existing, duplicate, "division", {"waiting room"})
    _copy_if_missing(existing, duplicate, "program")
    _copy_if_missing(existing, duplicate, "order_number")

    if not existing.order_date and duplicate.order_date:
        existing.order_date = duplicate.order_date

    if (
        existing.created_at
        and duplicate.created_at
        and duplicate.created_at < existing.created_at
    ):
        existing.created_at = duplicate.created_at


def _serialize_player(player):
    registrations = sorted(
        player.registrations,
        key=lambda r: (
            r.season or "",
            r.sport or "",
            r.division or "",
            r.id or 0,
        ),
        reverse=True,
    )
    return {
        "id": player.id,
        "name": player.full_name,
        "dateOfBirth": date_of_birth_iso(player.date_of_birth),
        "birthYear": player.birth_year,
        "jersey": player.jersey_number,
        "email": player.parent_email,
        "isHighSchool": bool(player.is_high_school),
        "locked": bool(player.locked),
        "registrations": [{
            "id": reg.id,
            "sport": reg.sport,
            "division": reg.division,
            "year": _season_year(reg),
            "season": reg.season,
            "emailSent": bool(reg.confirmation_sent),
        } for reg in registrations],
    }


@router.post("/players/merge")
def merge_players(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """Merge duplicate player records into the selected player."""
    keep_player_id = payload.get("keep_player_id", payload.get("keepPlayerId"))
    merge_player_ids = payload.get("merge_player_ids", payload.get("mergePlayerIds", []))

    try:
        keep_player_id = int(keep_player_id)
        merge_player_ids = [int(player_id) for player_id in merge_player_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Valid player IDs are required")

    merge_player_ids = list(dict.fromkeys(merge_player_ids))

    if not merge_player_ids:
        raise HTTPException(status_code=400, detail="Choose at least one player to merge")
    if keep_player_id in merge_player_ids:
        raise HTTPException(status_code=400, detail="The player to keep cannot also be merged")

    all_player_ids = [keep_player_id] + merge_player_ids
    players = db.query(Player).options(joinedload(Player.registrations)).filter(
        Player.id.in_(all_player_ids)
    ).all()
    players_by_id = {player.id: player for player in players}
    missing_ids = [player_id for player_id in all_player_ids if player_id not in players_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Player not found: {missing_ids[0]}")

    keep_player = players_by_id[keep_player_id]
    duplicate_players = [players_by_id[player_id] for player_id in merge_player_ids]
    kept_registrations = {
        _registration_key(reg): reg
        for reg in keep_player.registrations
    }

    moved_registrations = 0
    combined_registrations = 0
    deleted_players = 0
    updated_fields = []

    try:
        for duplicate_player in duplicate_players:
            if not keep_player.date_of_birth and duplicate_player.date_of_birth:
                keep_player.date_of_birth = duplicate_player.date_of_birth
                updated_fields.append("date_of_birth")
            if keep_player.birth_year is None and duplicate_player.birth_year is not None:
                keep_player.birth_year = duplicate_player.birth_year
                updated_fields.append("birth_year")
            if (keep_player.jersey_number is None or keep_player.jersey_number == 0) and duplicate_player.jersey_number:
                keep_player.jersey_number = duplicate_player.jersey_number
                updated_fields.append("jersey_number")
            if _is_blankish(keep_player.parent_email) and not _is_blankish(duplicate_player.parent_email):
                keep_player.parent_email = duplicate_player.parent_email
                updated_fields.append("parent_email")
            if duplicate_player.is_high_school and not keep_player.is_high_school:
                keep_player.is_high_school = True
                updated_fields.append("is_high_school")
            if duplicate_player.locked and not keep_player.locked:
                keep_player.locked = True
                updated_fields.append("locked")

            for duplicate_reg in list(duplicate_player.registrations):
                key = _registration_key(duplicate_reg)
                existing_reg = kept_registrations.get(key)

                if existing_reg:
                    _merge_registration(existing_reg, duplicate_reg)
                    combined_registrations += 1
                else:
                    duplicate_reg.player = keep_player
                    kept_registrations[key] = duplicate_reg
                    moved_registrations += 1

            db.flush()
            db.delete(duplicate_player)
            deleted_players += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    merged_player = db.query(Player).options(joinedload(Player.registrations)).filter(
        Player.id == keep_player_id
    ).first()

    return {
        "success": True,
        "keptPlayerId": keep_player_id,
        "deletedPlayers": deleted_players,
        "movedRegistrations": moved_registrations,
        "combinedRegistrations": combined_registrations,
        "updatedFields": sorted(set(updated_fields)),
        "player": _serialize_player(merged_player),
    }

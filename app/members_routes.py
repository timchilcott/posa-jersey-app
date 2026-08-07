"""
Members directory routes — sync and API for the members page.
"""
import logging
import threading
from datetime import date
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from app.database import get_db, SessionLocal
from app.models_members import Member, MemberGuardian
from app.models import Player, Registration
from app.player_dates import date_of_birth_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["members"])

# Track background sync status
_sync_status = {
    "running": False,
    "results": None,
    "error": None,
}


def _run_sync_background(force: bool = False):
    """Run members sync in background thread with its own DB session."""
    global _sync_status
    db = SessionLocal()
    try:
        from app.services.members_sync import sync_members
        results = sync_members(db, force=force)
        _sync_status["results"] = results
        _sync_status["error"] = None
    except Exception as e:
        logger.error(f"Background members sync failed: {e}", exc_info=True)
        _sync_status["error"] = str(e)
        _sync_status["results"] = None
    finally:
        db.close()
        _sync_status["running"] = False


@router.post("/api/members/sync")
def members_sync(force: bool = False):
    """Kick off members sync in background thread. Returns immediately.
    Pass ?force=true to re-fetch all profiles (picks up name changes, etc.).
    """
    from app.services.sportsengine import is_configured

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "SportsEngine not configured"},
        )

    if _sync_status["running"]:
        return {"status": "already_running"}

    _sync_status["running"] = True
    _sync_status["results"] = None
    _sync_status["error"] = None

    thread = threading.Thread(target=_run_sync_background, kwargs={"force": force}, daemon=True)
    thread.start()

    return {"status": "started", "mode": "full" if force else "incremental"}


@router.get("/api/members/sync-status")
def members_sync_status():
    """Poll for background sync completion."""
    if _sync_status["running"]:
        return {"status": "running"}
    if _sync_status["error"]:
        return {"status": "error", "detail": _sync_status["error"]}
    if _sync_status["results"]:
        return {"status": "success", **_sync_status["results"]}
    return {"status": "idle"}


@router.get("/api/members")
def list_members(db: Session = Depends(get_db)):
    """Return all members with their guardians and matched player data."""
    members = (
        db.query(Member)
        .order_by(Member.last_name, Member.first_name)
        .all()
    )

    # Load guardians for all members in one query
    member_ids = [m.id for m in members]
    guardians = (
        db.query(MemberGuardian)
        .filter(MemberGuardian.member_id.in_(member_ids))
        .all()
    ) if member_ids else []

    # Group guardians by member_id
    guardians_by_member = {}
    for g in guardians:
        guardians_by_member.setdefault(g.member_id, []).append({
            "id": g.id,
            "firstName": g.first_name,
            "lastName": g.last_name,
            "email": g.email,
            "phone": g.phone,
            "photoUrl": g.photo_url,
            "type": g.guardian_type,
        })

    # Load all players with registrations for name matching
    players = (
        db.query(Player)
        .options(joinedload(Player.registrations))
        .all()
    )

    # Build lookup: lowercase full_name -> player
    player_lookup = {}
    for p in players:
        key = (p.full_name or "").strip().lower()
        if key:
            player_lookup[key] = p

    def _is_child(member):
        """Determine if a member is a child (under 18) based on date of birth."""
        if not member.date_of_birth:
            # No DOB — fall back to whether they have guardians in DB
            return bool(guardians_by_member.get(member.id))
        try:
            # date_of_birth may be a string "YYYY-MM-DD" or a date object
            dob = member.date_of_birth
            if isinstance(dob, str):
                parts = dob.split("-")
                dob = date(int(parts[0]), int(parts[1]), int(parts[2]))
            today = date.today()
            age = today.year - dob.year - (
                (today.month, today.day) < (dob.month, dob.day)
            )
            return age < 18
        except Exception:
            return bool(guardians_by_member.get(member.id))

    result = []
    for m in members:
        # Match member to player by name (case-insensitive)
        member_full = f"{m.first_name} {m.last_name}".strip().lower()
        matched_player = player_lookup.get(member_full)
        is_child = _is_child(m)

        entry = {
            "id": m.id,
            "seProfileId": m.se_profile_id,
            "firstName": m.first_name,
            "lastName": m.last_name,
            "middleName": m.middle_name,
            "preferredName": m.preferred_name,
            "suffix": m.suffix,
            "email": m.email,
            "phone": m.phone,
            "dateOfBirth": m.date_of_birth,
            "gender": m.gender,
            "graduationYear": m.graduation_year,
            "photoUrl": m.photo_url,
            "address": {
                "address1": m.address1,
                "address2": m.address2,
                "city": m.city,
                "state": m.state,
                "postalCode": m.postal_code,
                "country": m.country,
            } if m.address1 or m.city else None,
            "memberships": m.memberships,
            "isChild": is_child,
            "guardians": guardians_by_member.get(m.id, []) if is_child else [],
            "player": None,
        }

        if matched_player:
            entry["player"] = {
                "id": matched_player.id,
                "jerseyNumber": matched_player.jersey_number,
                "dateOfBirth": date_of_birth_iso(matched_player.date_of_birth),
                "birthYear": matched_player.birth_year,
                "parentEmail": matched_player.parent_email,
                "locked": matched_player.locked,
                "registrations": [
                    {
                        "id": r.id,
                        "sport": r.sport,
                        "division": r.division,
                        "season": r.season,
                        "program": r.program,
                    }
                    for r in matched_player.registrations
                ],
            }

        result.append(entry)

    return {"members": result, "total": len(result)}

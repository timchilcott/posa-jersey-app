"""
Members directory routes — sync and API for the members page.
"""
import logging
import threading
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.models_members import Member, MemberGuardian

logger = logging.getLogger(__name__)

router = APIRouter(tags=["members"])

# Track background sync status
_sync_status = {
    "running": False,
    "results": None,
    "error": None,
}


def _run_sync_background():
    """Run members sync in a background thread with its own DB session."""
    global _sync_status
    db = SessionLocal()
    try:
        from app.services.members_sync import sync_members
        results = sync_members(db)
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
def members_sync():
    """Kick off members sync in background thread. Returns immediately."""
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

    thread = threading.Thread(target=_run_sync_background, daemon=True)
    thread.start()

    return {"status": "started"}


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
    """Return all members with their guardians for the directory page."""
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

    result = []
    for m in members:
        result.append({
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
            "guardians": guardians_by_member.get(m.id, []),
        })

    return {"members": result, "total": len(result)}

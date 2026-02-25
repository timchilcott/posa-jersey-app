"""
Members directory routes — sync and API for the members page.
"""
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models_members import Member, MemberGuardian

logger = logging.getLogger(__name__)

router = APIRouter(tags=["members"])


@router.post("/api/members/sync")
def members_sync(db: Session = Depends(get_db)):
    """Pull all member profiles from SportsEngine."""
    from app.services.sportsengine import is_configured
    from app.services.members_sync import sync_members

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "SportsEngine not configured"},
        )

    try:
        results = sync_members(db)
        return {"status": "success", **results}
    except Exception as e:
        logger.error(f"Members sync failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)},
        )


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

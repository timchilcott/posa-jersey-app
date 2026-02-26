"""
Seasons routes — teams, rosters, standings, and sync for the seasons page.
"""
import json
import logging
import threading
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, SessionLocal
from app.models_seasons import Team, TeamRoster, TeamStaff
from app.models_members import Member
from app.models import Player, Registration
from app.models_events import Event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["seasons"])

# Track background sync status
_sync_status = {
    "running": False,
    "results": None,
    "error": None,
}


def _run_sync_background():
    """Run teams sync in a background thread with its own DB session."""
    global _sync_status
    db = SessionLocal()
    try:
        from app.services.sportsengine import sync_all_teams
        results = sync_all_teams(db)
        _sync_status["results"] = results
        _sync_status["error"] = None
    except Exception as e:
        logger.error(f"Background teams sync failed: {e}", exc_info=True)
        _sync_status["error"] = str(e)
        _sync_status["results"] = None
    finally:
        db.close()
        _sync_status["running"] = False


@router.post("/api/seasons/sync")
def seasons_sync():
    """Kick off teams sync in background thread. Returns immediately."""
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


@router.get("/api/seasons/sync-status")
def seasons_sync_status():
    """Poll for background sync completion."""
    if _sync_status["running"]:
        return {"status": "running"}
    if _sync_status["error"]:
        return {"status": "error", "detail": _sync_status["error"]}
    if _sync_status["results"]:
        return {"status": "success", **_sync_status["results"]}
    return {"status": "idle"}


@router.get("/api/seasons/teams")
def list_teams(
    sport: Optional[str] = None,
    season_name: Optional[str] = None,
    division_name: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return all teams with roster/staff counts and filters."""
    query = db.query(Team).order_by(Team.sport, Team.season_name, Team.name)

    if sport:
        query = query.filter(func.lower(Team.sport) == sport.lower())
    if season_name:
        query = query.filter(Team.season_name == season_name)
    if division_name:
        query = query.filter(Team.division_name == division_name)
    if status:
        query = query.filter(func.lower(Team.status) == status.lower())
    if search:
        query = query.filter(Team.name.ilike(f"%{search}%"))

    teams = query.all()
    team_ids = [t.id for t in teams]

    # Count roster and staff per team in bulk
    roster_counts = {}
    staff_counts = {}
    if team_ids:
        for row in db.query(TeamRoster.team_id, func.count(TeamRoster.id)).filter(
            TeamRoster.team_id.in_(team_ids)
        ).group_by(TeamRoster.team_id).all():
            roster_counts[row[0]] = row[1]

        for row in db.query(TeamStaff.team_id, func.count(TeamStaff.id)).filter(
            TeamStaff.team_id.in_(team_ids)
        ).group_by(TeamStaff.team_id).all():
            staff_counts[row[0]] = row[1]

    result = []
    for t in teams:
        result.append({
            "id": t.id,
            "seTeamId": t.se_team_id,
            "name": t.name,
            "status": t.status,
            "sport": t.sport,
            "rosterStatus": t.roster_status,
            "approved": t.approved,
            "logoUrl": t.logo_url,
            "seasonName": t.season_name,
            "divisionName": t.division_name,
            "playerCount": roster_counts.get(t.id, 0),
            "staffCount": staff_counts.get(t.id, 0),
        })

    # Build available filter options
    all_sports = sorted(set(t.sport for t in teams if t.sport))
    all_seasons = sorted(set(t.season_name for t in teams if t.season_name))
    all_divisions = sorted(set(t.division_name for t in teams if t.division_name))
    all_statuses = sorted(set(t.status for t in teams if t.status))

    return {
        "teams": result,
        "total": len(result),
        "availableSports": all_sports,
        "availableSeasons": all_seasons,
        "availableDivisions": all_divisions,
        "availableStatuses": all_statuses,
    }


@router.get("/api/seasons/teams/{team_id}")
def get_team_detail(team_id: int, db: Session = Depends(get_db)):
    """Return a single team with full roster and staff, cross-linked to Members/Players."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return JSONResponse(status_code=404, content={"error": "Team not found"})

    # Load roster and staff
    roster = db.query(TeamRoster).filter(TeamRoster.team_id == team_id).order_by(
        TeamRoster.last_name, TeamRoster.first_name
    ).all()
    staff = db.query(TeamStaff).filter(TeamStaff.team_id == team_id).order_by(
        TeamStaff.last_name, TeamStaff.first_name
    ).all()

    # Cross-link roster players to Members via se_profile_id
    profile_ids = [r.se_profile_id for r in roster if r.se_profile_id]
    profile_ids += [s.se_profile_id for s in staff if s.se_profile_id]
    members_by_profile = {}
    if profile_ids:
        members = db.query(Member).filter(Member.se_profile_id.in_([str(pid) for pid in profile_ids])).all()
        for m in members:
            members_by_profile[str(m.se_profile_id)] = m

    # Cross-link to Players by name for POSA jersey numbers
    players = db.query(Player).all()
    player_lookup = {}
    for p in players:
        key = (p.full_name or "").strip().lower()
        if key:
            player_lookup[key] = p

    def _serialize_roster(r):
        entry = {
            "id": r.id,
            "firstName": r.first_name,
            "lastName": r.last_name,
            "jerseyNumber": r.jersey_number,
            "rosterStatus": r.roster_status,
            "seProfileId": r.se_profile_id,
            "member": None,
            "posaJersey": None,
        }
        # Cross-ref member
        if r.se_profile_id and str(r.se_profile_id) in members_by_profile:
            m = members_by_profile[str(r.se_profile_id)]
            entry["member"] = {
                "email": m.email,
                "phone": m.phone,
                "photoUrl": m.photo_url,
            }
        # Cross-ref POSA player
        full = f"{r.first_name} {r.last_name}".strip().lower()
        matched = player_lookup.get(full)
        if matched:
            entry["posaJersey"] = matched.jersey_number
        return entry

    def _serialize_staff(s):
        entry = {
            "id": s.id,
            "firstName": s.first_name,
            "lastName": s.last_name,
            "title": s.title,
            "rosterStatus": s.roster_status,
            "seProfileId": s.se_profile_id,
            "member": None,
        }
        if s.se_profile_id and str(s.se_profile_id) in members_by_profile:
            m = members_by_profile[str(s.se_profile_id)]
            entry["member"] = {
                "email": m.email,
                "phone": m.phone,
                "photoUrl": m.photo_url,
            }
        return entry

    return {
        "team": {
            "id": team.id,
            "seTeamId": team.se_team_id,
            "name": team.name,
            "status": team.status,
            "sport": team.sport,
            "rosterStatus": team.roster_status,
            "approved": team.approved,
            "logoUrl": team.logo_url,
            "seasonName": team.season_name,
            "divisionName": team.division_name,
        },
        "players": [_serialize_roster(r) for r in roster],
        "staff": [_serialize_staff(s) for s in staff],
    }


@router.get("/api/seasons/standings")
def get_standings(
    sport: str = Query(..., description="Sport to compute standings for"),
    db: Session = Depends(get_db),
):
    """Compute standings from completed game events."""
    events = (
        db.query(Event)
        .filter(
            func.lower(Event.event_type) == "game",
            func.lower(Event.status) == "completed",
            func.lower(Event.sport) == sport.lower(),
        )
        .all()
    )

    # Build standings: team_name -> stats
    standings = {}

    for event in events:
        teams_data = event.teams
        if not teams_data or not isinstance(teams_data, list) or len(teams_data) != 2:
            continue

        t1 = teams_data[0]
        t2 = teams_data[1]
        name1 = t1.get("name")
        name2 = t2.get("name")
        score1 = t1.get("score")
        score2 = t2.get("score")

        if not name1 or not name2:
            continue
        if score1 is None or score2 is None:
            continue

        try:
            s1 = int(score1)
            s2 = int(score2)
        except (ValueError, TypeError):
            continue

        # Initialize teams
        for name in [name1, name2]:
            if name not in standings:
                standings[name] = {
                    "team": name,
                    "logoUrl": t1.get("logoUrl") if name == name1 else t2.get("logoUrl"),
                    "w": 0, "l": 0, "t": 0, "gf": 0, "ga": 0,
                }

        # Record results
        standings[name1]["gf"] += s1
        standings[name1]["ga"] += s2
        standings[name2]["gf"] += s2
        standings[name2]["ga"] += s1

        if s1 > s2:
            standings[name1]["w"] += 1
            standings[name2]["l"] += 1
        elif s2 > s1:
            standings[name2]["w"] += 1
            standings[name1]["l"] += 1
        else:
            standings[name1]["t"] += 1
            standings[name2]["t"] += 1

    # Compute derived fields and sort
    result = []
    for entry in standings.values():
        entry["gd"] = entry["gf"] - entry["ga"]
        entry["pts"] = entry["w"] * 3 + entry["t"]
        entry["gp"] = entry["w"] + entry["l"] + entry["t"]
        result.append(entry)

    # Sort: pts desc, then gd desc, then gf desc
    result.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))

    # Add rank
    for i, entry in enumerate(result):
        entry["rank"] = i + 1

    return {"standings": result, "sport": sport, "gamesProcessed": len(events)}

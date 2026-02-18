"""
Sync routes - wires up SportsEngine sync to actual HTTP endpoints.

Add to main.py:
    from app.sync_routes import router as sync_router
    app.include_router(sync_router)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Player, Registration

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


@router.post("/sync/pull")
def sync_pull(db: Session = Depends(get_db)):
    """
    Pull all registrations from SportsEngine.
    This is the endpoint the admin UI's "Sync SportsEngine" button calls.
    """
    from app.services.sportsengine import is_configured, sync_all_registrations

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "detail": "SportsEngine integration not configured. Set SPORTSENGINE_CLIENT_ID, SPORTSENGINE_CLIENT_SECRET, and SPORTSENGINE_ORG_ID.",
            },
        )

    try:
        results = sync_all_registrations(db)
        return {
            "status": "success",
            "created": results["new_players"],
            "updated": results["existing_players"],
            "new_registrations": results["new_registrations"],
            "updated_registrations": results["updated_registrations"],
            "forms_processed": results["forms_processed"],
            "errors": len(results["errors"]),
            "error_details": results["errors"][:10],  # Cap at 10 for readability
        }
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)},
        )


@router.post("/sync/pull/{registration_id}")
def sync_pull_one(registration_id: str, db: Session = Depends(get_db)):
    """Sync a single registration form by ID."""
    from app.services.sportsengine import is_configured, sync_registration

    if not is_configured():
        raise HTTPException(status_code=400, detail="SportsEngine not configured")

    try:
        results = sync_registration(registration_id, db)
        return {
            "status": "success",
            "created": results["new_players"],
            "updated": results["existing_players"],
            "errors": len(results["errors"]),
        }
    except Exception as e:
        logger.error(f"Sync failed for {registration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/debug/player-lookup")
def debug_player_lookup(name: str = "", email: str = "", db: Session = Depends(get_db)):
    """
    Debug endpoint: look up a player by name or email and show ALL their data.
    Usage: /api/debug/player-lookup?name=John  or  ?email=parent@example.com
    """
    from fastapi.responses import HTMLResponse

    query = db.query(Player)
    if name:
        query = query.filter(Player.full_name.ilike(f"%{name}%"))
    if email:
        query = query.filter(Player.parent_email.ilike(f"%{email}%"))

    players = query.all()

    lines = [
        "<h2>Player Lookup</h2>",
        f"<p>Query: name='{name}' email='{email}' → {len(players)} result(s)</p>",
    ]

    for p in players:
        regs = (
            db.query(Registration)
            .filter(Registration.player_id == p.id)
            .order_by(Registration.created_at.desc())
            .all()
        )
        lines.append(f"<h3>{p.full_name} (ID: {p.id})</h3>")
        lines.append("<table border='1' cellpadding='5'>")
        lines.append(
            "<tr><th>Field</th><th>Value</th></tr>"
        )
        lines.append(f"<tr><td>birth_year</td><td>{p.birth_year}</td></tr>")
        lines.append(f"<tr><td>jersey_number</td><td>{p.jersey_number}</td></tr>")
        lines.append(f"<tr><td>parent_email</td><td>{p.parent_email}</td></tr>")
        lines.append(f"<tr><td>locked</td><td>{p.locked}</td></tr>")
        lines.append(f"<tr><td>grade</td><td>{getattr(p, 'grade', 'N/A')}</td></tr>")
        lines.append("</table>")

        if regs:
            lines.append(f"<h4>Registrations ({len(regs)})</h4>")
            lines.append("<table border='1' cellpadding='5'>")
            lines.append(
                "<tr><th>ID</th><th>sport</th><th>season</th><th>division</th>"
                "<th>program</th><th>confirmation_sent</th><th>created_at</th></tr>"
            )
            for r in regs:
                lines.append(
                    f"<tr><td>{r.id}</td><td>{repr(r.sport)}</td>"
                    f"<td>{repr(r.season)}</td><td>{repr(r.division)}</td>"
                    f"<td>{r.program}</td><td>{r.confirmation_sent}</td>"
                    f"<td>{r.created_at}</td></tr>"
                )
            lines.append("</table>")
        else:
            lines.append("<p><em>No registrations</em></p>")

        lines.append("<hr>")

    # Also show any potential duplicates (case differences, etc.)
    if name and players:
        all_similar = (
            db.query(Player)
            .filter(func.lower(Player.full_name).contains(name.lower()))
            .all()
        )
        if len(all_similar) > len(players):
            lines.append("<h3>⚠️ Similar names (possible duplicates)</h3><ul>")
            for p in all_similar:
                lines.append(
                    f"<li>ID {p.id}: {repr(p.full_name)} — email: {p.parent_email}</li>"
                )
            lines.append("</ul>")

    return HTMLResponse(
        f"<html><body style='font-family: monospace; padding: 20px;'>{''.join(lines)}</body></html>"
    )


@router.get("/api/debug/sport-season-mismatches")
def debug_sport_season_mismatches(db: Session = Depends(get_db)):
    """
    Debug endpoint: find registrations with inconsistent sport casing
    or season format issues.
    """
    from fastapi.responses import HTMLResponse
    from sqlalchemy import text

    # Sport casing inconsistencies
    sport_rows = db.execute(text("""
        SELECT sport, COUNT(*) as cnt
        FROM registrations
        GROUP BY sport
        ORDER BY LOWER(sport), sport
    """)).fetchall()

    # Season format inconsistencies
    season_rows = db.execute(text("""
        SELECT season, sport, COUNT(*) as cnt
        FROM registrations
        GROUP BY season, sport
        ORDER BY sport, season
    """)).fetchall()

    lines = ["<h2>Sport Casing</h2><table border='1' cellpadding='5'>"]
    lines.append("<tr><th>sport (raw)</th><th>count</th></tr>")
    for row in sport_rows:
        lines.append(f"<tr><td>{repr(row[0])}</td><td>{row[1]}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Season Formats</h2><table border='1' cellpadding='5'>")
    lines.append("<tr><th>season</th><th>sport</th><th>count</th></tr>")
    for row in season_rows:
        lines.append(f"<tr><td>{repr(row[0])}</td><td>{repr(row[1])}</td><td>{row[2]}</td></tr>")
    lines.append("</table>")

    return HTMLResponse(
        f"<html><body style='font-family: monospace; padding: 20px;'>{''.join(lines)}</body></html>"
    )

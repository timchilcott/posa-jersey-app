"""
Sync routes - wires up SportsEngine sync to actual HTTP endpoints.

Add to main.py:
    from app.sync_routes import router as sync_router
    app.include_router(sync_router)

Routes:
    POST /sync/pull              - Admin UI "Sync SportsEngine" button
    POST /sync/pull/{id}         - Sync a single registration form
    POST /sportsengine/webhook   - Incoming webhook from SportsEngine
    GET  /sportsengine/status    - Connection status check
    GET  /sportsengine/registrations - List available registration forms
    POST /sportsengine/sync      - Sync (used by sportsengine.html page)
    POST /sync/events            - Pull events from SportsEngine
    GET  /api/debug/player-lookup
    GET  /api/debug/sport-season-mismatches
"""
import os
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, SessionLocal
from app.models import Player, Registration

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


# ------------------------------------------------------------------
# Background task helpers — each creates its own DB session so the
# request session can close immediately.
# ------------------------------------------------------------------
def _bg_sync_registrations():
    """Run full registration sync in background with its own DB session."""
    db = SessionLocal()
    try:
        from app.services.sportsengine import sync_all_registrations
        results = sync_all_registrations(db)
        logger.info(
            f"BG registration sync done: "
            f"{results['new_players']} new, {results['existing_players']} updated, "
            f"{len(results['errors'])} errors"
        )
    except Exception as e:
        logger.error(f"BG registration sync failed: {e}", exc_info=True)
    finally:
        db.close()


def _bg_sync_events():
    """Run full event sync in background with its own DB session."""
    db = SessionLocal()
    try:
        from app.services.sportsengine import sync_all_events
        results = sync_all_events(db)
        logger.info(
            f"BG event sync done: "
            f"{results['new_events']} new, {results['updated_events']} updated, "
            f"{len(results['errors'])} errors"
        )
    except Exception as e:
        logger.error(f"BG event sync failed: {e}", exc_info=True)
    finally:
        db.close()


def _bg_sync_all():
    """Run both registration + event sync in background."""
    _bg_sync_registrations()
    _bg_sync_events()


# ------------------------------------------------------------------
# Primary sync endpoint (admin UI button)
# ------------------------------------------------------------------
@router.post("/sync/pull")
def sync_pull(background_tasks: BackgroundTasks):
    """
    Pull all registrations from SportsEngine.
    This is the endpoint the admin UI's "Sync SportsEngine" button calls.
    Responds immediately; sync runs in background.
    """
    from app.services.sportsengine import is_configured

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "detail": "SportsEngine integration not configured. Set SPORTSENGINE_CLIENT_ID, SPORTSENGINE_CLIENT_SECRET, and SPORTSENGINE_ORG_ID.",
            },
        )

    background_tasks.add_task(_bg_sync_registrations)
    return {"status": "accepted", "message": "Registration sync started in background"}


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


# ------------------------------------------------------------------
# SportsEngine webhook (receives POST from SportsEngine servers)
# ------------------------------------------------------------------
@router.post("/sportsengine/webhook")
async def sportsengine_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive webhook notifications from SportsEngine.
    Responds immediately with 200 and runs sync in background so
    SportsEngine doesn't time out waiting for a response.
    """
    from app.services.sportsengine import is_configured

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    resource_type = payload.get("resourceType") or payload.get("type") or "unknown"
    operation = payload.get("resourceOperation") or payload.get("operation") or payload.get("action") or "unknown"
    resource_id = payload.get("resourceId") or payload.get("id") or "unknown"

    logger.info(f"WEBHOOK: Received — operation={operation} type={resource_type} id={resource_id}")

    if not is_configured():
        logger.warning("Webhook received but SportsEngine not configured")
        return {"status": "ignored", "reason": "not configured"}

    # Respond immediately, sync in background
    background_tasks.add_task(_bg_sync_all)
    return {"status": "accepted", "message": "Sync started in background"}


# ------------------------------------------------------------------
# SportsEngine status / registrations / sync (used by sportsengine.html)
# ------------------------------------------------------------------
@router.get("/sportsengine/status")
def sportsengine_status():
    """Check SportsEngine connection status."""
    from app.services.sportsengine import is_configured

    client_id = os.getenv("SPORTSENGINE_CLIENT_ID")
    client_secret = os.getenv("SPORTSENGINE_CLIENT_SECRET")
    org_id = os.getenv("SPORTSENGINE_ORG_ID")

    result = {
        "configured": is_configured(),
        "client_id_set": bool(client_id),
        "client_secret_set": bool(client_secret),
        "org_id": org_id,
        "authenticated": False,
        "auth_error": None,
    }

    if is_configured():
        try:
            from app.services.sportsengine import get_access_token
            get_access_token()
            result["authenticated"] = True
        except Exception as e:
            result["auth_error"] = str(e)

    return result


@router.get("/sportsengine/registrations")
def sportsengine_registrations():
    """List available registration forms from SportsEngine."""
    from app.services.sportsengine import is_configured, get_all_registrations, extract_sport_from_registration_name

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "SportsEngine not configured"},
        )

    try:
        forms = get_all_registrations()
        for form in forms:
            form["sport"] = extract_sport_from_registration_name(form["name"])
            form["resultsCompleted"] = form.get("count", 0)
        return {"status": "success", "registrations": forms}
    except Exception as e:
        logger.error(f"Failed to load registrations: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)},
        )


@router.post("/sportsengine/sync")
async def sportsengine_sync(request: Request, background_tasks: BackgroundTasks):
    """
    Sync endpoint used by the sportsengine.html management page.
    Accepts optional { "registration_id": "..." } to sync a single form.
    Single-form sync still runs synchronously (fast); full sync is background.
    """
    from app.services.sportsengine import is_configured, sync_registration

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "SportsEngine not configured"},
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    reg_id = body.get("registration_id")

    # Single-form sync is fast enough to run inline
    if reg_id:
        db = SessionLocal()
        try:
            results = sync_registration(reg_id, db)
            return {
                "status": "success",
                "created": results["new_players"],
                "updated": results["existing_players"],
                "new_registrations": results["new_registrations"],
                "updated_registrations": results["updated_registrations"],
                "errors": len(results["errors"]),
                "error_details": results["errors"][:10],
            }
        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"status": "error", "detail": str(e)},
            )
        finally:
            db.close()

    # Full sync → background
    background_tasks.add_task(_bg_sync_registrations)
    return {"status": "accepted", "message": "Registration sync started in background"}


# ------------------------------------------------------------------
# Event sync endpoint
# ------------------------------------------------------------------
@router.post("/sync/events")
def sync_events(background_tasks: BackgroundTasks):
    """Pull events from SportsEngine. Responds immediately; sync runs in background."""
    from app.services.sportsengine import is_configured

    if not is_configured():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "SportsEngine not configured"},
        )

    background_tasks.add_task(_bg_sync_events)
    return {"status": "accepted", "message": "Event sync started in background"}


# ------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------
@router.get("/api/debug/schema-introspect")
def debug_schema_introspect(type_name: str = "Team"):
    """
    Introspect a GraphQL type to discover all available fields.
    Also recursively resolves OBJECT-type fields one level deep.
    Usage: /api/debug/schema-introspect?type_name=Brand
    """
    from app.services.sportsengine import is_configured, graphql_query

    if not is_configured():
        return {"error": "SportsEngine not configured"}

    query = """
    query IntrospectType($typeName: String!) {
        __type(name: $typeName) {
            name
            kind
            fields {
                name
                type {
                    name
                    kind
                    ofType { name kind ofType { name kind ofType { name kind } } }
                }
            }
        }
    }
    """
    try:
        data = graphql_query(query, {"typeName": type_name})
        type_info = (data or {}).get("__type")

        if not type_info:
            return {"error": f"Type '{type_name}' not found", "hint": "Try 'Event', 'Team', 'Brand', or 'Query'"}

        # For each OBJECT field, fetch its sub-fields too
        nested = {}
        for field in (type_info.get("fields") or []):
            ft = field.get("type", {})
            # Resolve through NON_NULL / LIST wrappers
            resolved = ft
            while resolved and resolved.get("kind") in ("NON_NULL", "LIST"):
                resolved = resolved.get("ofType") or {}
            resolved_name = resolved.get("name") if resolved else None
            resolved_kind = resolved.get("kind") if resolved else None

            if resolved_kind == "OBJECT" and resolved_name:
                try:
                    sub = graphql_query(query, {"typeName": resolved_name})
                    sub_type = (sub or {}).get("__type")
                    if sub_type and sub_type.get("fields"):
                        nested[field["name"]] = {
                            "typeName": resolved_name,
                            "fields": [f["name"] for f in sub_type["fields"]],
                        }
                except Exception:
                    pass

        result = {"type": type_info}
        if nested:
            result["nestedObjectFields"] = nested
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/debug/player-lookup")
def debug_player_lookup(name: str = "", email: str = "", db: Session = Depends(get_db)):
    """
    Debug endpoint: look up a player by name or email and show ALL their data.
    Usage: /api/debug/player-lookup?name=John  or  ?email=parent@example.com
    """
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
        lines.append("<tr><th>Field</th><th>Value</th></tr>")
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
    """Find registrations with inconsistent sport casing or season format issues."""
    from sqlalchemy import text

    sport_rows = db.execute(text("""
        SELECT sport, COUNT(*) as cnt
        FROM registrations
        GROUP BY sport
        ORDER BY LOWER(sport), sport
    """)).fetchall()

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

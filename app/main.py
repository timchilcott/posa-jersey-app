import os
import pathlib
from datetime import datetime
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from jinja2 import Environment, FileSystemLoader
from app.database import get_db, engine
from app.models import Base, Player, Registration, EmailTemplate
from app.api_routes import router as admin_api_router
from app.sync_routes import router as sync_router
from app.inventory_routes import router as inventory_router
from app.events_routes import router as events_router

Base.metadata.create_all(bind=engine)
app = FastAPI(title="POSA Jersey Management")

# Static files (sidebar.js, etc.)
_static_dir = pathlib.Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(admin_api_router)
app.include_router(sync_router)
app.include_router(inventory_router)
app.include_router(events_router)

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"


def _read_template(name: str) -> str:
    with open(_TEMPLATES_DIR / name, "r") as f:
        return f.read()


@app.get("/")
async def home():
    return {"status": "ok"}

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return HTMLResponse(_read_template("players_page.html"))

@app.get("/admin/volunteers", response_class=HTMLResponse)
async def admin_volunteers(request: Request):
    return HTMLResponse(_read_template("volunteers_page.html"))

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page():
    return HTMLResponse(_read_template("inventory_page.html"))

@app.get("/events", response_class=HTMLResponse)
async def events_page():
    return HTMLResponse(_read_template("events_page.html"))

@app.get("/sportsengine", response_class=HTMLResponse)
async def sportsengine_page():
    return HTMLResponse(_read_template("sportsengine.html"))

@app.get("/email-templates", response_class=HTMLResponse)
async def email_templates_page(db: Session = Depends(get_db)):
    standard_template = db.query(EmailTemplate).filter(
        EmailTemplate.name == "standard_confirmation"
    ).first()
    pines_template = db.query(EmailTemplate).filter(
        EmailTemplate.name == "pines_confirmation"
    ).first()
    _jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)))
    template = _jinja_env.get_template("email_templates.html")
    html = template.render(
        standard_template=standard_template,
        pines_template=pines_template,
    )
    return HTMLResponse(html)

@app.post("/email-templates")
async def save_email_template(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    name = data.get("name")
    subject = data.get("subject")
    body_html = data.get("body_html")
    template = db.query(EmailTemplate).filter(EmailTemplate.name == name).first()
    if template:
        template.subject = subject
        template.body_html = body_html
    else:
        template = EmailTemplate(name=name, subject=subject, body_html=body_html)
        db.add(template)
    db.commit()
    return {"success": True}

@app.post("/api/players/{player_id}/set-volunteer")
async def set_volunteer(player_id: int, request: Request, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return {"success": False, "error": "Player not found"}

    data = await request.json()
    player.locked = bool(data.get("is_volunteer", False))
    db.commit()

    return {"success": True, "is_volunteer": player.locked}

@app.put("/api/players/{player_id}")
async def update_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return {"success": False, "error": "Player not found"}

    data = await request.json()

    if "full_name" in data:
        player.full_name = data["full_name"]
    if "parent_email" in data:
        player.parent_email = data["parent_email"]
    if "birth_year" in data:
        player.birth_year = data["birth_year"]
    if "jersey_number" in data and data["jersey_number"] is not None:
        player.jersey_number = int(data["jersey_number"])

    if "birth_year" in data and data["birth_year"]:
        if not player.jersey_number or player.jersey_number == 0:
            max_jersey = db.query(func.max(Player.jersey_number)).filter(
                Player.birth_year == data["birth_year"]
            ).scalar()

            try:
                next_num = int(max_jersey or 0) + 1
            except:
                next_num = 1

            player.jersey_number = next_num

    db.commit()

    return {
        "success": True,
        "jersey": player.jersey_number
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/debug/seasons", response_class=HTMLResponse)
async def debug_seasons(db: Session = Depends(get_db)):
    """Show all distinct season values and counts"""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT season, sport,
               EXTRACT(YEAR FROM created_at)::int as reg_year,
               COUNT(*) as cnt
        FROM registrations
        GROUP BY season, sport, reg_year
        ORDER BY reg_year DESC, sport, season
    """)).fetchall()

    lines = ["<h2>Season Values in Database</h2><table border='1' cellpadding='5'>"]
    lines.append("<tr><th>Season</th><th>Sport</th><th>Reg Year</th><th>Count</th></tr>")
    for row in rows:
        season_val = repr(row[0])
        lines.append(f"<tr><td>{season_val}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>")
    lines.append("</table>")

    return f"<html><body style='font-family: monospace; padding: 20px;'>{''.join(lines)}</body></html>"

@app.get("/api/debug/divisions", response_class=HTMLResponse)
async def debug_divisions(db: Session = Depends(get_db)):
    """Show all distinct division values"""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT division, sport, COUNT(*) as cnt
        FROM registrations
        GROUP BY division, sport
        ORDER BY sport, division
    """)).fetchall()

    lines = ["<h2>Division Values in Database</h2><table border='1' cellpadding='5'>"]
    lines.append("<tr><th>Division</th><th>Sport</th><th>Count</th></tr>")
    for row in rows:
        lines.append(f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td></tr>")
    lines.append("</table>")

    return f"<html><body style='font-family: monospace; padding: 20px;'>{''.join(lines)}</body></html>"


@app.get("/api/cleanup-registrations", response_class=HTMLResponse)
async def cleanup_registrations(db: Session = Depends(get_db)):
    """One-time fix: clean up bad registration data. DELETE AFTER USE."""
    from sqlalchemy import text

    fixes = [
        ("UPDATE registrations SET season = 'Spring 2026' WHERE LOWER(sport) = 'soccer' AND TRIM(season) = '2026'", "soccer '2026' → 'Spring 2026'"),
    ]

    results = []
    for sql, label in fixes:
        count = db.execute(text(sql)).rowcount
        results.append(f"{label}: {count} rows affected")

    db.commit()

    detail = "<br>".join(results)
    return f"""<html><body style='font-family: monospace; padding: 20px;'>
        <h2>Registration Cleanup Complete</h2>
        <p>{detail}</p>
        <hr>
        <p><a href='/api/debug/seasons'>View current season values</a></p>
        <p><a href='/api/debug/divisions'>View current divisions</a></p>
        <p style='color: red; font-weight: bold;'>DELETE THIS ENDPOINT AFTER CONFIRMING!</p>
    </body></html>"""

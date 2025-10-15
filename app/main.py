from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime
from pydantic import BaseModel
from typing import List
import os
import csv
import io

from .database import Base, engine, SessionLocal
from .models import Player, Registration, User, EmailTemplate
from .auth import authenticate_user, create_user
from .email import (
    send_confirmation_email,
    send_pines_confirmation_email,
    process_inbound_email,
    save_inbound_email,
    normalize_division,
    DIVISION_ORDER,
)

# ---------------------------------------------------------------------
# Global Config
# ---------------------------------------------------------------------
CURRENT_SEASON = os.getenv("CURRENT_SEASON", "2025")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "secret-key"))
templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------
class PlayerUpdate(BaseModel):
    full_name: str
    birth_year: int | None
    jersey_number: int
    parent_email: str

class PlayerSportsUpdate(BaseModel):
    sports: List[str]

class DivisionUpdate(BaseModel):
    division: str

class PlayerLock(BaseModel):
    locked: bool

class PlayerInlineCreate(BaseModel):
    full_name: str
    birth_year: int | None
    parent_email: str
    sport: str
    division: str
    season: str

class EmailTemplateUpdate(BaseModel):
    name: str
    subject: str
    body_html: str

# ---------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------
def calculate_u_division(birth_year: int, season_year: int = None) -> str:
    """Calculate display-only U-division label (does not modify player data)."""
    if season_year is None:
        season_year = int(CURRENT_SEASON) if CURRENT_SEASON.isdigit() else 2025
    u_number = (season_year - birth_year) + 1
    return f"U{u_number}"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_login(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )

@app.on_event("startup")
def ensure_admin_user() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).first():
            email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            password = os.getenv("ADMIN_PASSWORD", "admin")
            create_user(db, email, password)
    finally:
        db.close()

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "POSA Jersey App is running!"}

# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=400
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/admin", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# ---------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------
@app.get("/invite", response_class=HTMLResponse)
def invite_form(request: Request):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    return templates.TemplateResponse("invite_user.html", {"request": request, "error": None})

@app.post("/invite")
def invite_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)

    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "invite_user.html",
            {"request": request, "error": "User already exists"},
            status_code=400
        )
    create_user(db, email, password)
    return RedirectResponse("/admin", status_code=302)

# ---------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, view: str = "birthyear", db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)

    # Get all players
    players = db.query(Player).all()
    season_year = int(CURRENT_SEASON) if CURRENT_SEASON.isdigit() else 2025

    # Calculate birth year counts (exclude Waiting Room players)
    birth_year_counts = {}
    for player in players:
        if player.birth_year:
            # Only count if they have at least one non-Waiting Room registration
            has_valid_division = any(
                r.division not in {"", "Unknown", "Waiting Room"} 
                for r in player.registrations
            )
            if has_valid_division:
                year = player.birth_year
                birth_year_counts[year] = birth_year_counts.get(year, 0) + 1
    
    # Sort birth years from newest to oldest
    birth_year_counts = dict(sorted(birth_year_counts.items(), reverse=True))

    # Identify duplicates by birth year + sport + jersey number
    birth_year_sport_jersey = defaultdict(list)
    for p in players:
        for reg in p.registrations:
            key = ((reg.sport or "").strip().lower(), p.birth_year, p.jersey_number)
            birth_year_sport_jersey[key].append(p.id)
    duplicate_ids = {pid for ids in birth_year_sport_jersey.values() if len(ids) > 1 for pid in ids}

    EXCLUDED_DIVISIONS = {"", "Unknown"}
    counted_player_ids = set()

    # ------------------- DIVISION VIEW -------------------
    if view == "division":
        players_by_division = defaultdict(list)
        unassigned_players = []
        waiting_room_players = []
        
        for p in players:
            sports = sorted({(r.sport or "").strip().lower() for r in p.registrations if r.sport})
            divisions = sorted({(r.division or "").strip() for r in p.registrations if r.division})
            confirmation_sent = any(r.confirmation_sent for r in p.registrations)
            reg_id = p.registrations[0].id if p.registrations else None

            # Check if player is in Waiting Room
            if "Waiting Room" in divisions:
                player_data = {
                    "id": p.id,
                    "registration_id": reg_id,
                    "full_name": p.full_name,
                    "birth_year": p.birth_year,
                    "parent_email": p.parent_email,
                    "jersey_number": p.jersey_number,
                    "sports": sports,
                    "division": "Waiting Room",
                    "divisions": divisions,
                    "confirmation_sent": confirmation_sent,
                    "locked": p.locked,
                    "is_duplicate": p.id in duplicate_ids,
                }
                waiting_room_players.append(player_data)
                continue

            valid_divisions = [d for d in divisions if d not in EXCLUDED_DIVISIONS]
            primary_division = valid_divisions[0] if valid_divisions else "Unknown"

            player_data = {
                "id": p.id,
                "registration_id": reg_id,
                "full_name": p.full_name,
                "birth_year": p.birth_year,
                "parent_email": p.parent_email,
                "jersey_number": p.jersey_number,
                "sports": sports,
                "division": primary_division,
                "divisions": divisions,
                "confirmation_sent": confirmation_sent,
                "locked": p.locked,
                "is_duplicate": p.id in duplicate_ids,
            }

            if primary_division in EXCLUDED_DIVISIONS:
                unassigned_players.append(player_data)
            else:
                players_by_division[primary_division].append(player_data)
                counted_player_ids.add(p.id)

        sorted_players = dict(sorted(players_by_division.items(), key=lambda x: DIVISION_ORDER.get(x[0], 999)))

        for division, plist in sorted_players.items():
            plist.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))

        return templates.TemplateResponse("admin.html", {
            "request": request,
            "view": "division",
            "players_by_group": sorted_players,
            "group_list": list(sorted_players.keys()),
            "unassigned_players": unassigned_players,
            "waiting_room_players": waiting_room_players,
            "total_players": len(counted_player_ids),
            "birth_year_counts": birth_year_counts,
        })

    # ------------------- BIRTH YEAR VIEW -------------------
    players_by_birth_year = defaultdict(list)
    waiting_room_players = []
    
    for p in players:
        sports = sorted({(r.sport or "").strip().lower() for r in p.registrations if r.sport})
        confirmation_sent = any(r.confirmation_sent for r in p.registrations)
        reg_id = p.registrations[0].id if p.registrations else None
        divisions = {(r.division or "").strip() for r in p.registrations if r.division}

        # Check if player is in Waiting Room
        if "Waiting Room" in divisions:
            player_data = {
                "id": p.id,
                "registration_id": reg_id,
                "full_name": p.full_name,
                "birth_year": p.birth_year,
                "parent_email": p.parent_email,
                "jersey_number": p.jersey_number,
                "sports": sports,
                "division": "Waiting Room",
                "confirmation_sent": confirmation_sent,
                "locked": p.locked,
                "is_duplicate": p.id in duplicate_ids,
            }
            waiting_room_players.append(player_data)
            continue

        player_data = {
            "id": p.id,
            "registration_id": reg_id,
            "full_name": p.full_name,
            "birth_year": p.birth_year,
            "parent_email": p.parent_email,
            "jersey_number": p.jersey_number,
            "sports": sports,
            "division": (p.registrations[0].division if p.registrations else ""),
            "confirmation_sent": confirmation_sent,
            "locked": p.locked,
            "is_duplicate": p.id in duplicate_ids,
        }

        if p.birth_year:
            players_by_birth_year[p.birth_year].append(player_data)
            counted_player_ids.add(p.id)

    birth_year_list = sorted(players_by_birth_year.keys(), reverse=True)
    birth_year_labels = {
        by: f"{by} / {calculate_u_division(by, season_year)}"
        for by in birth_year_list
    }

    for plist in players_by_birth_year.values():
        plist.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))

    sorted_players = dict(sorted(players_by_birth_year.items(), reverse=True))

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "view": "birthyear",
        "players_by_group": sorted_players,
        "group_list": birth_year_list,
        "birth_year_labels": birth_year_labels,
        "unassigned_players": [],
        "waiting_room_players": waiting_room_players,
        "total_players": len(counted_player_ids),
        "birth_year_counts": birth_year_counts,
    })

# ---------------------------------------------------------------------
# Player Management
# ---------------------------------------------------------------------
@app.post("/players/inline")
def create_player_inline(payload: PlayerInlineCreate, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc

    from .services.assign import assign_jersey_number
    
    # Check if player already exists
    existing = db.query(Player).filter(Player.full_name == payload.full_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Player already exists")
    
    # Assign jersey number
    jersey = assign_jersey_number(db, payload.birth_year)
    
    # Create player
    player = Player(
        full_name=payload.full_name,
        birth_year=payload.birth_year,
        parent_email=payload.parent_email,
        jersey_number=jersey
    )
    db.add(player)
    db.flush()
    
    # Create registration
    reg = Registration(
        player_id=player.id,
        program=f"{payload.season} {payload.sport}",
        division=payload.division,
        sport=payload.sport.strip().lower(),
        season=payload.season,
        confirmation_sent=False
    )
    db.add(reg)
    db.commit()
    db.refresh(player)
    db.refresh(reg)
    
    return {
        "id": player.id,
        "registration_id": reg.id,
        "full_name": player.full_name,
        "birth_year": player.birth_year,
        "parent_email": player.parent_email,
        "jersey_number": player.jersey_number,
        "sport": payload.sport.strip().lower(),
        "division": payload.division
    }

@app.put("/players/{player_id}")
def update_player(player_id: int, payload: PlayerUpdate, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    player = db.query(Player).get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # If birth year is being set for the first time and they don't have a jersey, assign one
    if payload.birth_year and not player.birth_year and not player.jersey_number:
        from .services.assign import assign_jersey_number
        player.jersey_number = assign_jersey_number(db, payload.birth_year)
    
    player.full_name = payload.full_name
    player.birth_year = payload.birth_year
    player.jersey_number = payload.jersey_number
    player.parent_email = payload.parent_email
    
    db.commit()
    return {"status": "updated"}

@app.delete("/players/{player_id}")
def delete_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    player = db.query(Player).get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    db.delete(player)
    db.commit()
    return {"status": "deleted"}

@app.put("/players/{player_id}/sports")
def update_player_sports(player_id: int, payload: PlayerSportsUpdate, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    player = db.query(Player).get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get current registrations
    current_regs = db.query(Registration).filter(Registration.player_id == player_id).all()
    current_sports = {reg.sport.lower() for reg in current_regs}
    new_sports = {sport.lower() for sport in payload.sports}
    
    # Remove sports that are no longer selected
    for reg in current_regs:
        if reg.sport.lower() not in new_sports:
            db.delete(reg)
    
    # Add new sports
    season_year = int(CURRENT_SEASON) if CURRENT_SEASON.isdigit() else datetime.now().year
    for sport in new_sports:
        if sport not in current_sports:
            new_reg = Registration(
                player_id=player_id,
                program=f"{season_year} {sport}",
                division=current_regs[0].division if current_regs else "",
                sport=sport,
                season=str(season_year),
                confirmation_sent=False
            )
            db.add(new_reg)
    
    db.commit()
    
    # Get updated registrations
    updated_regs = db.query(Registration).filter(Registration.player_id == player_id).all()
    return {
        "sports": [reg.sport for reg in updated_regs],
        "registration_id": updated_regs[0].id if updated_regs else None
    }

@app.put("/players/{player_id}/lock")
def lock_player(player_id: int, payload: PlayerLock, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    player = db.query(Player).get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    player.locked = payload.locked
    db.commit()
    return {"locked": player.locked}

# ---------------------------------------------------------------------
# Registration Management
# ---------------------------------------------------------------------
@app.put("/registrations/{reg_id}/division")
def update_registration_division(reg_id: int, payload: DivisionUpdate, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    from .services.assign import assign_jersey_number
    
    reg = db.query(Registration).get(reg_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    old_division = reg.division
    new_division = normalize_division(payload.division, reg.player.birth_year)
    
    # Update division
    reg.division = new_division
    
    # If moving OUT of Waiting Room and player needs a jersey, assign one
    if old_division == "Waiting Room" and new_division != "Waiting Room":
        if not reg.player.jersey_number and reg.player.birth_year:
            new_jersey = assign_jersey_number(db, reg.player.birth_year)
            reg.player.jersey_number = new_jersey
    # If moving to a different division (not from Waiting Room), reassign jersey number
    elif old_division != "Waiting Room" and old_division != new_division:
        new_jersey = assign_jersey_number(db, reg.player.birth_year)
        reg.player.jersey_number = new_jersey
    
    db.commit()
    return {
        "division": reg.division,
        "jersey_number": reg.player.jersey_number
    }

@app.post("/registrations/{reg_id}/send_email")
def send_registration_email(reg_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    reg = db.query(Registration).get(reg_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    # Get registrations that came in together (same order)
    parent_email = reg.player.parent_email
    
    # If this registration has an order number, batch by order number
    # Otherwise, only send this single registration
    if reg.order_number:
        all_regs = (
            db.query(Registration)
            .join(Player)
            .filter(Player.parent_email == parent_email)
            .filter(Registration.order_number == reg.order_number)
            .filter(Registration.confirmation_sent == False)
            .all()
        )
    else:
        # No order number means this was manually added, only send this one
        all_regs = [reg] if not reg.confirmation_sent else []
    
    if not all_regs:
        return {"status": "no unsent registrations"}
    
    # Group by division type (Pines HS vs others)
    pines_regs = []
    standard_regs = []
    
    for r in all_regs:
        if r.division == "Pend Oreille Pines (High School Club Team)":
            pines_regs.append(r)
        else:
            standard_regs.append(r)
    
    # Send Pines email if applicable
    if pines_regs:
        pines_players = [
            {
                "name": r.player.full_name,
                "jersey_number": r.player.jersey_number,
                "sport": r.sport
            }
            for r in pines_regs
        ]
        send_pines_confirmation_email(parent_email, pines_players, pines_regs, db)
    
    # Send standard email if applicable
    if standard_regs:
        standard_players = [
            {
                "name": r.player.full_name,
                "jersey_number": r.player.jersey_number,
                "sport": r.sport
            }
            for r in standard_regs
        ]
        from .email import PROMO_CODES
        promo_code = PROMO_CODES.get(len(standard_players))
        send_confirmation_email(parent_email, standard_players, promo_code, standard_regs, db)
    
    return {"status": "sent"}

# ---------------------------------------------------------------------
# Email Template Management
# ---------------------------------------------------------------------
@app.get("/email-templates", response_class=HTMLResponse)
def email_templates_page(request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    
    standard_template = db.query(EmailTemplate).filter(
        EmailTemplate.name == "standard_confirmation"
    ).first()
    
    pines_template = db.query(EmailTemplate).filter(
        EmailTemplate.name == "pines_confirmation"
    ).first()
    
    return templates.TemplateResponse("email_templates.html", {
        "request": request,
        "standard_template": standard_template,
        "pines_template": pines_template
    })

@app.post("/email-templates")
def save_email_template(payload: EmailTemplateUpdate, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    template = db.query(EmailTemplate).filter(
        EmailTemplate.name == payload.name
    ).first()
    
    if template:
        template.subject = payload.subject
        template.body_html = payload.body_html
        template.updated_at = datetime.utcnow()
    else:
        template = EmailTemplate(
            name=payload.name,
            subject=payload.subject,
            body_html=payload.body_html
        )
        db.add(template)
    
    db.commit()
    return {"status": "saved"}

# ---------------------------------------------------------------------
# Email Webhook
# ---------------------------------------------------------------------
@app.post("/email/receive")
async def receive_email(request: Request, db: Session = Depends(get_db)):
    """Receive inbound emails from SendGrid or similar service."""
    body = await request.body()
    email_text = body.decode('utf-8')
    
    # Save for debugging in development
    if os.getenv("ENV") != "production":
        save_inbound_email(email_text)
    
    # Process the email
    process_inbound_email(email_text, db)
    
    return {"status": "received"}

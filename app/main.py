from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime
from pydantic import BaseModel
import os
import csv
import io

from .database import Base, engine, SessionLocal
from .models import Player, Registration, User
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

    # Get all players, all time
    players = db.query(Player).all()
    season_year = int(CURRENT_SEASON) if CURRENT_SEASON.isdigit() else 2025

    missing_emails = sum(1 for p in players if not p.parent_email)
    missing_jerseys = sum(1 for p in players if not p.jersey_number)

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
        for p in players:
            sports = sorted({(r.sport or "").strip().lower() for r in p.registrations if r.sport})
            divisions = sorted({(r.division or "").strip() for r in p.registrations if r.division})
            confirmation_sent = any(r.confirmation_sent for r in p.registrations)
            reg_id = p.registrations[0].id if p.registrations else None

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
            "total_players": len(counted_player_ids),
            "missing_emails": missing_emails,
            "missing_jerseys": missing_jerseys,
        })

    # ------------------- BIRTH YEAR VIEW -------------------
    players_by_birth_year = defaultdict(list)
    for p in players:
        sports = sorted({(r.sport or "").strip().lower() for r in p.registrations if r.sport})
        confirmation_sent = any(r.confirmation_sent for r in p.registrations)
        reg_id = p.registrations[0].id if p.registrations else None

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
        "total_players": len(counted_player_ids),
        "missing_emails": missing_emails,
        "missing_jerseys": missing_jerseys,
    })

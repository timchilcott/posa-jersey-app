from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .database import Base, engine, SessionLocal
from .models import Player, Registration, User, EmailTemplate
from .auth import authenticate_user, create_user
from .services.assign import assign_jersey_number
from .email import (
    send_confirmation_email,
    send_pines_confirmation_email,
    process_inbound_email,
    save_inbound_email,
    normalize_division,
    PROMO_CODES,
    DIVISION_ORDER,
)
from collections import defaultdict
from datetime import datetime
import csv
import io
import os

# ---------------------------------------------------------------------
# Global Config
# ---------------------------------------------------------------------
CURRENT_SEASON = os.getenv("CURRENT_SEASON", "2025")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "secret-key"))
templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------
def calculate_u_division(birth_year: int, season_year: int = None) -> str:
    """Calculate U-division based on birth year with POSA-specific override for 2022 → U3."""
    if season_year is None:
        season_year = int(CURRENT_SEASON) if CURRENT_SEASON.isdigit() else 2025

    # POSA-specific U3 rule for 2022 births
    if birth_year == 2022:
        return "U3"

    u_number = (season_year - birth_year) + 1
    return f"U{u_number}"


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_login(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "POSA Jersey App is running!"}


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=400)
    request.session["user_id"] = user.id
    return RedirectResponse("/admin", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/invite", response_class=HTMLResponse)
def invite_form(request: Request):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    return templates.TemplateResponse("invite_user.html", {"request": request, "error": None})


@app.post("/invite")
def invite_user(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse("invite_user.html", {"request": request, "error": "User already exists"}, status_code=400)
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

    query = db.query(Player).join(Player.registrations)
    season_year = int(CURRENT_SEASON) if CURRENT_SEASON.isdigit() else 2025

    # ✅ Show all registrations by default
    selected_season = request.query_params.get("season")
    if selected_season:
        query = query.filter(Registration.season.ilike(f"%{selected_season}%"))

    players = query.distinct().all()

    EXCLUDED_DIVISIONS = {"", "Unknown"}
    missing_emails = 0
    missing_jerseys = 0
    counted_player_ids = set()

    for player in players:
        if not player.parent_email:
            missing_emails += 1
        if not player.jersey_number:
            missing_jerseys += 1

    birth_year_sport_jersey = defaultdict(list)
    for player in players:
        if player.birth_year and player.jersey_number:
            for reg in player.registrations:
                key = ((reg.sport or "").strip().lower(), player.birth_year, player.jersey_number)
                birth_year_sport_jersey[key].append(player.id)

    duplicate_player_ids = {pid for ids in birth_year_sport_jersey.values() if len(ids) > 1 for pid in ids}

    # ---- Division View ----
    if view == "division":
        division_order = DIVISION_ORDER.copy()
        players_by_division = defaultdict(list)
        unassigned_players = []
        player_seen = {}

        for player in players:
            sports = set()
            divisions = set()
            reg_ids = []
            confirmation_sent_any = False

            for reg in player.registrations:
                sport_key = (reg.sport or "").strip().lower()
                division_raw = (reg.division or "").strip()
                division = normalize_division(division_raw, player.birth_year)
                sports.add(sport_key)
                divisions.add(division)
                reg_ids.append(reg.id)
                if reg.confirmation_sent:
                    confirmation_sent_any = True

            valid_divisions = [d for d in divisions if d not in EXCLUDED_DIVISIONS]
            primary_division = sorted(valid_divisions, key=lambda x: division_order.get(x, 999))[0] if valid_divisions else ""

            if player.id in player_seen:
                continue
            player_seen[player.id] = primary_division

            player_data = {
                "id": player.id,
                "registration_id": reg_ids[0] if reg_ids else None,
                "full_name": player.full_name,
                "birth_year": player.birth_year,
                "parent_email": player.parent_email,
                "jersey_number": player.jersey_number,
                "sports": sorted(list(sports)),
                "division": primary_division,
                "divisions": sorted(list(divisions)),
                "confirmation_sent": confirmation_sent_any,
                "locked": player.locked,
                "is_duplicate": player.id in duplicate_player_ids,
            }

            if primary_division in EXCLUDED_DIVISIONS:
                unassigned_players.append(player_data)
                continue

            counted_player_ids.add(player.id)
            players_by_division[primary_division].append(player_data)

        division_list = sorted(players_by_division.keys(), key=lambda x: division_order.get(x, 999))

        for division, plist in players_by_division.items():
            plist.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))

        sorted_players = dict(sorted(players_by_division.items(), key=lambda x: division_order.get(x[0], 999)))

        return templates.TemplateResponse("admin.html", {
            "request": request,
            "view": "division",
            "players_by_group": sorted_players,
            "group_list": division_list,
            "unassigned_players": unassigned_players,
            "total_players": len(counted_player_ids),
            "missing_emails": missing_emails,
            "missing_jerseys": missing_jerseys,
        })

    # ---- Birth Year View ----
    players_by_birth_year = defaultdict(list)
    unassigned_players = []
    player_seen = set()

    for player in players:
        if player.id in player_seen:
            continue
        sports = set()
        divisions = set()
        reg_ids = []
        confirmation_sent_any = False
        for reg in player.registrations:
            sport_key = (reg.sport or "").strip().lower()
            division_raw = (reg.division or "").strip()
            division = normalize_division(division_raw, player.birth_year)
            sports.add(sport_key)
            divisions.add(division)
            reg_ids.append(reg.id)
            if reg.confirmation_sent:
                confirmation_sent_any = True
        valid_divisions = [d for d in divisions if d not in EXCLUDED_DIVISIONS]
        primary_division = sorted(valid_divisions, key=lambda x: DIVISION_ORDER.get(x, 999))[0] if valid_divisions else ""
        player_seen.add(player.id)
        player_data = {
            "id": player.id,
            "registration_id": reg_ids[0] if reg_ids else None,
            "full_name": player.full_name,
            "birth_year": player.birth_year,
            "parent_email": player.parent_email,
            "jersey_number": player.jersey_number,
            "sports": sorted(list(sports)),
            "division": primary_division,
            "confirmation_sent": confirmation_sent_any,
            "locked": player.locked,
            "is_duplicate": player.id in duplicate_player_ids,
        }
        if player.birth_year:
            counted_player_ids.add(player.id)
            players_by_birth_year[player.birth_year].append(player_data)

    birth_year_list = sorted(players_by_birth_year.keys(), reverse=True)
    birth_year_labels = {by: f"{by} / {calculate_u_division(by, season_year)}" for by in birth_year_list}
    for by, plist in players_by_birth_year.items():
        plist.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))
    sorted_players = dict(sorted(players_by_birth_year.items(), reverse=True))

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "view": "birthyear",
        "players_by_group": sorted_players,
        "group_list": birth_year_list,
        "birth_year_labels": birth_year_labels,
        "unassigned_players": unassigned_players,
        "total_players": len(counted_player_ids),
        "missing_emails": missing_emails,
        "missing_jerseys": missing_jerseys,
    })

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
# FASTAPI SETUP
# ---------------------------------------------------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "secret-key"))
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------
def calculate_u_division(birth_year: int, season_year: int = None) -> str:
    """Calculate U-division based on birth year using US Soccer guidelines,
    with POSA-specific override for 2022 births."""
    if season_year is None:
        season_year = 2025

    # POSA local rule: 2022 births = U3
    if birth_year == 2022:
        return "U3"

    u_number = (season_year - birth_year) + 1
    return f"U{u_number}"


@app.on_event("startup")
def ensure_admin_user() -> None:
    """Create initial admin user if none exist."""
    db = SessionLocal()
    try:
        if not db.query(User).first():
            email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            password = os.getenv("ADMIN_PASSWORD", "admin")
            create_user(db, email, password)
            print(f"[INFO] Created default admin user: {email}")
        print("[INFO] POSA local rule active: 2022 → U3")
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_login(request: Request):
    """Redirect to login if user not authenticated."""
    if not request.session.get("user_id"):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})

# ---------------------------------------------------------------------
# ROUTES
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
# ADMIN DASHBOARD — ALL SEASONS
# ---------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, view: str = "birthyear", db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)

    # Show all players across all seasons
    query = db.query(Player).join(Player.registrations)
    players = query.distinct().all()
    print(f"[INFO] Showing all players across all seasons: {len(players)} total.")

    EXCLUDED_DIVISIONS = {"", "Unknown"}
    missing_emails = 0
    missing_jerseys = 0
    counted_player_ids = set()

    for player in players:
        if not player.parent_email:
            missing_emails += 1
        if not player.jersey_number:
            missing_jerseys += 1

    # Detect duplicate jersey numbers within birth years and sports
    birth_year_sport_jersey = defaultdict(list)
    for player in players:
        if player.birth_year and player.jersey_number:
            for reg in player.registrations:
                sport_key = (reg.sport or "").strip().lower()
                key = (sport_key, player.birth_year, player.jersey_number)
                birth_year_sport_jersey[key].append(player.id)

    duplicate_player_ids = set()
    for key, player_ids in birth_year_sport_jersey.items():
        if len(player_ids) > 1:
            duplicate_player_ids.update(player_ids)

    # --- View by Division ---
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
            if valid_divisions:
                primary_division = sorted(valid_divisions, key=lambda x: division_order.get(x, 999))[0]
            else:
                primary_division = list(divisions)[0] if divisions else ""
            if player.id in player_seen:
                continue
            player_seen[player.id] = primary_division
            is_dup = player.id in duplicate_player_ids
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
                "is_duplicate": is_dup,
            }
            if primary_division in EXCLUDED_DIVISIONS:
                unassigned_players.append(player_data)
                continue
            counted_player_ids.add(player.id)
            players_by_division[primary_division].append(player_data)
        division_names = set(division_order.keys())
        for div in players_by_division.keys():
            name = (div or "").strip()
            if name not in EXCLUDED_DIVISIONS:
                division_names.add(name)
        division_list = sorted(
            division_names,
            key=lambda x: division_order.get(x, 999),
        )
        for division in division_list:
            players_by_division.setdefault(division, [])
        for division, player_list in players_by_division.items():
            player_list.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))
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

    # --- View by Birth Year ---
    else:
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
            if valid_divisions:
                primary_division = sorted(valid_divisions, key=lambda x: DIVISION_ORDER.get(x, 999))[0]
            else:
                primary_division = list(divisions)[0] if divisions else ""
            is_dup = player.id in duplicate_player_ids
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
                "is_duplicate": is_dup,
            }
            player_seen.add(player.id)
            if primary_division in EXCLUDED_DIVISIONS:
                unassigned_players.append(player_data)
                continue
            if player.birth_year:
                counted_player_ids.add(player.id)
                players_by_birth_year[player.birth_year].append(player_data)
        birth_year_list = sorted(players_by_birth_year.keys(), reverse=True)
        birth_year_labels = {
            by: f"{by} / {calculate_u_division(by)}"
            for by in birth_year_list
        }
        for birth_year in birth_year_list:
            players_by_birth_year.setdefault(birth_year, [])
        for birth_year, player_list in players_by_birth_year.items():
            player_list.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))
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

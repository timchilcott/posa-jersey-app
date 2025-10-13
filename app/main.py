from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
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
# AUTOMATIC SEASON DETECTION
# ---------------------------------------------------------------------
def get_current_season():
    """Detect the most recent season string from registrations."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT season FROM registrations WHERE season IS NOT NULL ORDER BY created_at DESC LIMIT 1;")
            ).fetchone()
            if result and result[0]:
                print(f"[INFO] Auto-detected CURRENT_SEASON = {result[0]}")
                return result[0]
    except Exception as e:
        print(f"[WARN] Could not detect season automatically: {e}")
    return "2024"  # fallback default

CURRENT_SEASON = get_current_season()

# ---------------------------------------------------------------------
# FASTAPI APP SETUP
# ---------------------------------------------------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "secret-key"))
templates = Jinja2Templates(directory="app/templates")

# Only create tables locally if no DB tables exist yet
if os.getenv("ENVIRONMENT", "development") == "development":
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------
def calculate_u_division(birth_year: int, season_year: int = None) -> str:
    """Calculate U-division based on birth year using US Soccer guidelines."""
    if season_year is None:
        try:
            season_year = int(str(CURRENT_SEASON)[:4])
        except Exception:
            season_year = 2025
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
# ADMIN DASHBOARD
# ---------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, view: str = "birthyear", db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)

    query = db.query(Player).join(Player.registrations)

    # Flexible season filtering
    if CURRENT_SEASON:
        season_filter = Registration.season.ilike(f"%{CURRENT_SEASON}%")
        filtered_players = query.filter(season_filter).distinct().all()
        if len(filtered_players) < 5:  # if too few found, fall back to all players
            print(f"[INFO] Found only {len(filtered_players)} for season {CURRENT_SEASON}, showing all instead.")
            players = query.distinct().all()
        else:
            players = filtered_players
    else:
        players = query.distinct().all()

    # Everything below here stays the same as before
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
                sport_key = (reg.sport or "").strip().lower()
                key = (sport_key, player.birth_year, player.jersey_number)
                birth_year_sport_jersey[key].append(player.id)

    duplicate_player_ids = set()
    for key, player_ids in birth_year_sport_jersey.items():
        if len(player_ids) > 1:
            duplicate_player_ids.update(player_ids)

    # (the rest of your existing admin_dashboard logic stays unchanged)
    # ↓↓↓ keep all grouping, template rendering, and stats exactly as in your version ↓↓↓
    # ---------------------------------------------------------------------
    # [Your original grouping and return code continues here...]
    # ---------------------------------------------------------------------

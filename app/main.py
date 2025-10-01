from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .database import Base, engine, SessionLocal
from .models import Player, Registration, User
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
import csv
import io
import os

CURRENT_SEASON = os.getenv("CURRENT_SEASON", "2024")
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "secret-key"))
templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)


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

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, view: str = "birthyear", db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    
    query = db.query(Player).join(Player.registrations)

    if CURRENT_SEASON:
        season_match = (
            db.query(Registration)
            .filter(Registration.season.ilike(f"%{CURRENT_SEASON}%"))
            .first()
        )
        if season_match:
            query = query.filter(
                Registration.season.ilike(f"%{CURRENT_SEASON}%")
            )

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

    # Detect duplicate jersey numbers within birth years
    birth_year_jersey_map = defaultdict(lambda: defaultdict(list))
    for player in players:
        if player.birth_year and player.jersey_number:
            for reg in player.registrations:
                sport_key = (reg.sport or "").strip().lower()
                birth_year_jersey_map[sport_key][player.birth_year].append({
                    'player_id': player.id,
                    'jersey_number': player.jersey_number
                })

    # Find duplicates
    duplicate_player_ids = set()
    for sport_jerseys in birth_year_jersey_map.values():
        for birth_year, player_list in sport_jerseys.items():
            jersey_counts = defaultdict(list)
            for p in player_list:
                jersey_counts[p['jersey_number']].append(p['player_id'])
            for jersey_num, player_ids in jersey_counts.items():
                if len(player_ids) > 1:
                    duplicate_player_ids.update(player_ids)

    if view == "division":
        # Original division-based view
        division_order = DIVISION_ORDER.copy()
        players_by_sport = defaultdict(lambda: defaultdict(list))
        unassigned_by_sport = defaultdict(list)

        for player in players:
            for reg in player.registrations:
                sport_key = (reg.sport or "").strip().lower()
                division_raw = (reg.division or "").strip()
                division = normalize_division(division_raw) if division_raw else ""
                
                player_data = {
                    "id": player.id,
                    "registration_id": reg.id,
                    "full_name": player.full_name,
                    "birth_year": player.birth_year,
                    "parent_email": player.parent_email,
                    "jersey_number": player.jersey_number,
                    "sport": sport_key,
                    "division": division,
                    "confirmation_sent": reg.confirmation_sent,
                    "locked": player.locked,
                    "is_duplicate": player.id in duplicate_player_ids,
                }
                
                if division in EXCLUDED_DIVISIONS:
                    unassigned_by_sport[sport_key].append(player_data)
                    continue
                    
                counted_player_ids.add(player.id)
                players_by_sport[sport_key][division].append(player_data)

        # Build list of all divisions
        division_names = set(division_order.keys())
        for divisions in players_by_sport.values():
            for div in divisions.keys():
                name = (div or "").strip()
                if name not in EXCLUDED_DIVISIONS:
                    division_names.add(name)
        division_list = sorted(
            division_names,
            key=lambda x: division_order.get(x, 999),
        )
        division_rank = {name: idx for idx, name in enumerate(division_list)}

        # Ensure each sport has entries for every division
        for sport in players_by_sport.keys():
            for division in division_list:
                players_by_sport[sport].setdefault(division, [])

        # Sort players within each division by jersey number
        for sport, divisions in players_by_sport.items():
            for division, player_list in divisions.items():
                player_list.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))

        sorted_players_by_sport = {}
        for sport, divisions in players_by_sport.items():
            sorted_divisions = dict(sorted(divisions.items(), key=lambda x: division_rank[x[0]]))
            sorted_players_by_sport[sport] = sorted_divisions

        return templates.TemplateResponse("admin.html", {
            "request": request,
            "view": "division",
            "players_by_sport": sorted_players_by_sport,
            "division_list": division_list,
            "unassigned_players_by_sport": unassigned_by_sport,
            "total_players": len(counted_player_ids),
            "missing_emails": missing_emails,
            "missing_jerseys": missing_jerseys,
        })
    
    else:
        # New birth year-based view
        players_by_sport = defaultdict(lambda: defaultdict(list))
        unassigned_by_sport = defaultdict(list)

        for player in players:
            for reg in player.registrations:
                sport_key = (reg.sport or "").strip().lower()
                division_raw = (reg.division or "").strip()
                division = normalize_division(division_raw) if division_raw else ""
                
                if division in EXCLUDED_DIVISIONS:
                    unassigned_by_sport[sport_key].append({
                        "id": player.id,
                        "registration_id": reg.id,
                        "full_name": player.full_name,
                        "birth_year": player.birth_year,
                        "parent_email": player.parent_email,
                        "jersey_number": player.jersey_number,
                        "sport": sport_key,
                        "division": division,
                        "confirmation_sent": reg.confirmation_sent,
                        "locked": player.locked,
                        "is_duplicate": player.id in duplicate_player_ids,
                    })
                    continue
                
                if player.birth_year:
                    counted_player_ids.add(player.id)
                    players_by_sport[sport_key][player.birth_year].append({
                        "id": player.id,
                        "registration_id": reg.id,
                        "full_name": player.full_name,
                        "birth_year": player.birth_year,
                        "parent_email": player.parent_email,
                        "jersey_number": player.jersey_number,
                        "sport": sport_key,
                        "division": division,
                        "confirmation_sent": reg.confirmation_sent,
                        "locked": player.locked,
                        "is_duplicate": player.id in duplicate_player_ids,
                    })

        # Get all birth years and sort them (newest to oldest)
        birth_years = set()
        for sport_data in players_by_sport.values():
            birth_years.update(sport_data.keys())
        birth_year_list = sorted(birth_years, reverse=True)

        # Ensure each sport has entries for every birth year
        for sport in players_by_sport.keys():
            for birth_year in birth_year_list:
                players_by_sport[sport].setdefault(birth_year, [])

        # Sort players within each birth year by jersey number
        for sport, birth_years_dict in players_by_sport.items():
            for birth_year, player_list in birth_years_dict.items():
                player_list.sort(key=lambda p: (p["jersey_number"] is None, p["jersey_number"]))

        sorted_players_by_sport = {}
        for sport, birth_years_dict in players_by_sport.items():
            sorted_birth_years = dict(sorted(birth_years_dict.items(), reverse=True))
            sorted_players_by_sport[sport] = sorted_birth_years

        return templates.TemplateResponse("admin.html", {
            "request": request,
            "view": "birthyear",
            "players_by_sport": sorted_players_by_sport,
            "birth_year_list": birth_year_list,
            "unassigned_players_by_sport": unassigned_by_sport,
            "total_players": len(counted_player_ids),
            "missing_emails": missing_emails,
            "missing_jerseys": missing_jerseys,
        })


@app.get("/players/new", response_class=HTMLResponse)
def new_player_form(request: Request):
    """Render form to add a player manually."""
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    return templates.TemplateResponse("new_player.html", {"request": request})


@app.post("/players/new")
def create_player_manual(
    request: Request,
    full_name: str = Form(...),
    birth_year: int = Form(None),
    parent_email: str = Form(...),
    sport: str = Form(...),
    division: str = Form(...),
    season: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create player and registration from form submission."""
    require_login(request)
    division = normalize_division(division)
    jersey_number = assign_jersey_number(db, birth_year)
    sport_normalized = sport.strip().lower()
    player = Player(
        full_name=full_name,
        birth_year=birth_year,
        parent_email=parent_email,
        jersey_number=jersey_number
    )
    db.add(player)
    db.flush()
    reg = Registration(
        player_id=player.id,
        program=f"{season} {sport}",
        division=division,
        sport=sport_normalized,
        season=season,
    )
    db.add(reg)
    db.commit()
    return RedirectResponse("/admin", status_code=302)

class PlayerUpdate(BaseModel):
    full_name: str
    birth_year: int | None
    parent_email: str
    jersey_number: int

@app.put("/players/{player_id}")
async def update_player(player_id: int, player: PlayerUpdate, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    db_player = db.get(Player, player_id)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    if db_player.locked:
        raise HTTPException(status_code=403, detail="Player is locked")
    db_player.full_name = player.full_name
    db_player.birth_year = player.birth_year
    db_player.parent_email = player.parent_email
    db_player.jersey_number = player.jersey_number
    db.commit()
    db.refresh(db_player)
    return db_player


class LockUpdate(BaseModel):
    locked: bool


@app.put("/players/{player_id}/lock")
def update_player_lock(player_id: int, lock: LockUpdate, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    db_player = db.get(Player, player_id)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    db_player.locked = lock.locked
    db.commit()
    return {"locked": db_player.locked}

class PlayerCreate(BaseModel):
    full_name: str
    birth_year: int | None
    parent_email: str

class InlinePlayerCreate(PlayerCreate):
    sport: str
    division: str
    season: str

@app.post("/players")
def create_player(player: PlayerCreate, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    jersey_number = assign_jersey_number(db, player.birth_year)
    db_player = Player(
        full_name=player.full_name,
        birth_year=player.birth_year,
        parent_email=player.parent_email,
        jersey_number=jersey_number
    )
    db.add(db_player)
    db.commit()
    db.refresh(db_player)
    return db_player


@app.post("/players/inline")
def create_player_inline(player: InlinePlayerCreate, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    division = normalize_division(player.division)
    jersey_number = assign_jersey_number(db, player.birth_year)
    db_player = Player(
        full_name=player.full_name,
        birth_year=player.birth_year,
        parent_email=player.parent_email,
        jersey_number=jersey_number,
    )
    db.add(db_player)
    db.flush()
    reg = Registration(
        player_id=db_player.id,
        program=f"{player.season} {player.sport}",
        division=division,
        sport=player.sport.strip().lower(),
        season=player.season,
    )
    db.add(reg)
    db.commit()
    return {
        "id": db_player.id,
        "registration_id": reg.id,
        "full_name": db_player.full_name,
        "birth_year": db_player.birth_year,
        "parent_email": db_player.parent_email,
        "jersey_number": db_player.jersey_number,
        "sport": player.sport.strip().lower(),
        "division": player.division,
        "confirmation_sent": reg.confirmation_sent,
    }


class DivisionUpdate(BaseModel):
    division: str


@app.put("/registrations/{registration_id}/division")
def move_player_division(
    registration_id: int,
    payload: DivisionUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update a player's registration division."""
    require_login(request)
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    if reg.player.locked:
        raise HTTPException(status_code=403, detail="Player is locked")

    new_division = normalize_division(payload.division)
    reg.division = new_division
    db.commit()
    db.refresh(reg)

    return {
        "id": reg.player.id,
        "registration_id": reg.id,
        "full_name": reg.player.full_name,
        "birth_year": reg.player.birth_year,
        "parent_email": reg.player.parent_email,
        "jersey_number": reg.player.jersey_number,
        "sport": reg.sport,
        "division": reg.division,
        "confirmation_sent": reg.confirmation_sent,
    }

@app.get("/export")
def export_players_csv(request: Request, db: Session = Depends(get_db)):
    require_login(request)
    players = db.query(Player).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Birth Year", "Parent Email", "Jersey Number"])
    for player in players:
        writer.writerow([player.full_name, player.birth_year or "", player.parent_email, player.jersey_number])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode()), media_type="text/csv")

@app.delete("/players/{player_id}")
def delete_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if player.locked:
        raise HTTPException(status_code=403, detail="Player is locked")
    db.delete(player)
    db.commit()
    return {"message": "Player deleted"}

@app.post("/email/receive")
async def receive_email(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    raw_email = form.get("email")

    if raw_email:
        save_inbound_email(raw_email)
        process_inbound_email(raw_email, db)
        return {"message": "Email received and processed"}
    else:
        return {"error": "No email content found in request"}


@app.post("/registrations/{registration_id}/send_email")
def send_registration_email(registration_id: int, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    reg = db.get(Registration, registration_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    if reg.player.locked:
        raise HTTPException(status_code=403, detail="Player is locked")
    parent_email = reg.player.parent_email
    regs = (
        db.query(Registration)
        .join(Registration.player)
        .filter(Player.parent_email == parent_email)
        .all()
    )
    pines_division = "Pend Oreille Pines (High School Club Team)"

    regular_regs = []
    pines_regs = []
    for r in regs:
        division = normalize_division(r.division)
        if division == pines_division:
            pines_regs.append(r)
        else:
            regular_regs.append(r)

    if regular_regs:
        promo_code = PROMO_CODES.get(len(regular_regs))
        players = [
            {"name": r.player.full_name, "jersey_number": r.player.jersey_number}
            for r in regular_regs
        ]
        send_confirmation_email(parent_email, players, promo_code, regular_regs, db)

    if pines_regs:
        players = [
            {"name": r.player.full_name, "jersey_number": r.player.jersey_number}
            for r in pines_regs
        ]
        send_pines_confirmation_email(parent_email, players, pines_regs, db)

    return {"message": "Email sent"}

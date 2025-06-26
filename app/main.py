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
from .email import send_confirmation_email, process_inbound_email, save_inbound_email
from collections import defaultdict
import csv
import io
import os

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
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    players = db.query(Player).all()
    division_order = {"U4": 0, "U6": 1, "U8": 2, "U10": 3, "U12": 4, "U14": 5}
    players_by_sport = defaultdict(lambda: defaultdict(list))
    missing_emails = 0
    missing_jerseys = 0

    for player in players:
        if not player.parent_email:
            missing_emails += 1
        if not player.jersey_number:
            missing_jerseys += 1

        for reg in player.registrations:
            sport_key = (reg.sport or "").strip().lower()
            players_by_sport[sport_key][reg.division].append({
                "id": player.id,
                "registration_id": reg.id,
                "full_name": player.full_name,
                "parent_email": player.parent_email,
                "jersey_number": player.jersey_number,
                "sport": sport_key,
                "division": reg.division,
                "confirmation_sent": reg.confirmation_sent,
            })

    sorted_players_by_sport = {}
    for sport, divisions in players_by_sport.items():
        sorted_divisions = dict(sorted(divisions.items(), key=lambda x: division_order.get(x[0], 999)))
        sorted_players_by_sport[sport] = sorted_divisions

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "players_by_sport": sorted_players_by_sport,
        "total_players": len(players),
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
    parent_email: str = Form(...),
    sport: str = Form(...),
    division: str = Form(...),
    season: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create player and registration from form submission."""
    require_login(request)
    jersey_number = assign_jersey_number(db, division)
    sport_normalized = sport.strip().lower()
    player = Player(full_name=full_name, parent_email=parent_email, jersey_number=jersey_number)
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
    parent_email: str
    jersey_number: int

@app.put("/players/{player_id}")
async def update_player(player_id: int, player: PlayerUpdate, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    db_player = db.query(Player).get(player_id)
    if db_player:
        db_player.full_name = player.full_name
        db_player.parent_email = player.parent_email
        db_player.jersey_number = player.jersey_number
        db.commit()
        db.refresh(db_player)
        return db_player
    else:
        raise HTTPException(status_code=404, detail="Player not found")

class PlayerCreate(BaseModel):
    full_name: str
    parent_email: str

@app.post("/players")
def create_player(player: PlayerCreate, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    dummy_division = "U6"
    jersey_number = assign_jersey_number(db, dummy_division)
    db_player = Player(
        full_name=player.full_name,
        parent_email=player.parent_email,
        jersey_number=jersey_number
    )
    db.add(db_player)
    db.commit()
    db.refresh(db_player)
    return db_player

@app.get("/export")
def export_players_csv(request: Request, db: Session = Depends(get_db)):
    require_login(request)
    players = db.query(Player).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Parent Email", "Jersey Number"])
    for player in players:
        writer.writerow([player.full_name, player.parent_email, player.jersey_number])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode()), media_type="text/csv")

@app.delete("/players/{player_id}")
def delete_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    require_login(request)
    player = db.query(Player).get(player_id)
    if player:
        db.delete(player)
        db.commit()
        return {"message": "Player deleted"}
    else:
        raise HTTPException(status_code=404, detail="Player not found")

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
    reg = db.query(Registration).get(registration_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    player = reg.player
    send_confirmation_email(
        player.parent_email,
        player.full_name,
        player.jersey_number,
        "https://your-order-url.com",
        reg,
        db,
    )
    return {"message": "Email sent"}

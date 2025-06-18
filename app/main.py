from fastapi import FastAPI, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from collections import defaultdict
import os
import csv
import io
import re

from .database import Base, engine, SessionLocal
from .models import Player, Registration
from .services.assign import assign_jersey_number
from .email import send_confirmation_email, process_inbound_email

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": "POSA Jersey App is running!"}

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    players = db.query(Player).all()
    division_order = {"U4": 0, "U6": 1, "U8": 2, "U10": 3, "U12": 4, "U14": 5}
    players_by_sport = defaultdict(lambda: defaultdict(list))

    for player in players:
        for reg in player.registrations:
            players_by_sport[reg.sport][reg.division].append({
                "id": player.id,
                "full_name": player.full_name,
                "parent_email": player.parent_email,
                "jersey_number": player.jersey_number,
                "sport": reg.sport,
                "division": reg.division,
            })

    sorted_players_by_sport = {}
    for sport, divisions in players_by_sport.items():
        sorted_divisions = dict(sorted(divisions.items(), key=lambda x: division_order.get(x[0], 999)))
        sorted_players_by_sport[sport] = sorted_divisions

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "players_by_sport": sorted_players_by_sport,
        "total_players": len(players),
    })

class PlayerCreate(BaseModel):
    full_name: str
    parent_email: str

@app.post("/players")
def create_player(player: PlayerCreate, db: Session = Depends(get_db)):
    # Assign jersey number based on dummy division or logic you prefer
    dummy_division = "U6"  # or any default you want; adjust as needed
    jersey_number = assign_jersey_number(db, dummy_division)
    db_player = Player(
        full_name=player.full_name,
        parent_email=player.parent_email,
        jersey_number=jersey_number
    )
    db.add(db_player)
    db.commit()
    db.refresh(db_player)
    send_confirmation_email(db_player.parent_email, db_player.full_name, db_player.jersey_number, order_url="https://your-order-url.com")
    return db_player

@app.get("/export")
def export_players_csv(db: Session = Depends(get_db)):
    players = db.query(Player).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Parent Email", "Jersey Number"])
    for player in players:
        writer.writerow([player.full_name, player.parent_email, player.jersey_number])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode()), media_type="text/csv")

@app.post("/delete/{player_id}")
def delete_player(player_id: int, db: Session = Depends(get_db)):
    player = db.query(Player).get(player_id)
    if player:
        db.delete(player)
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/edit/{player_id}")
def edit_player(
    player_id: int,
    full_name: str = Form(...),
    parent_email: str = Form(...),
    jersey_number: int = Form(...),
    db: Session = Depends(get_db),
):
    player = db.query(Player).get(player_id)
    if player:
        player.full_name = full_name
        player.parent_email = parent_email
        player.jersey_number = jersey_number
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/email/receive")
async def receive_email(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    raw_email = form.get("email")

    if raw_email:
        process_inbound_email(raw_email, db)
        return {"message": "Email received and processed"}
    else:
        return {"error": "No email content found in request"}

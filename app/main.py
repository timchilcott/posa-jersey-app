from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime
from pydantic import BaseModel
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
import os
import csv
import io
import logging

from .database import Base, engine, SessionLocal
from .models import Player, Registration, User, EmailTemplate
from .auth import authenticate_user, create_user
from .email import (
    send_confirmation_email,
    send_pines_confirmation_email,
    process_inbound_email,
    save_inbound_email,
    normalize_division,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Global Config
# ---------------------------------------------------------------------
CURRENT_SEASON = os.getenv("CURRENT_SEASON", "2025")

# Validate SECRET_KEY
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")
if SECRET_KEY == "secret-key":
    logger.warning("Using default SECRET_KEY - this is insecure for production!")

app = FastAPI()

# Enhanced session middleware configuration for better mobile compatibility
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="posa_session",
    max_age=3600 * 24,  # 24 hours
    same_site="lax",
    https_only=False  # Set to True if using HTTPS in production
)

# ---------------------------------------------------------------------
# Background Scheduler for SportsEngine Sync
# ---------------------------------------------------------------------
scheduler = AsyncIOScheduler()

def scheduled_sportsengine_sync():
    """Daily backup sync - catches anything webhooks missed."""
    try:
        # Import here to avoid circular imports
        from .services.sportsengine import get_all_registrations, sync_registration, is_configured
        import time
        
        if not is_configured():
            logger.debug("SportsEngine not configured, skipping scheduled sync")
            return
        
        logger.info("Starting scheduled SportsEngine sync...")
        db = SessionLocal()
        try:
            registrations = get_all_registrations()
            active_count = 0
            for reg in registrations:
                # Only sync active registrations (status 1)
                if reg.get("status") == 1:
                    # Add delay between registrations to avoid rate limits
                    if active_count > 0:
                        time.sleep(5)  # 5 seconds between registrations
                    
                    try:
                        result = sync_registration(str(reg["id"]), db)
                        logger.info(f"Scheduled sync {reg['name']}: {result}")
                        active_count += 1
                    except Exception as e:
                        logger.error(f"Scheduled sync error for {reg['name']}: {e}")
        finally:
            db.close()
        logger.info("Scheduled SportsEngine sync complete")
    except Exception as e:
        logger.error(f"Scheduled sync failed: {e}")

@app.on_event("startup")
async def start_scheduler():
    """Start the background scheduler when the app starts."""
    # Run every 30 minutes for reliable syncing
    scheduler.add_job(scheduled_sportsengine_sync, "interval", minutes=30, id="sportsengine_sync")
    scheduler.start()
    logger.info("Background scheduler started - SportsEngine sync every 30 minutes")

@app.on_event("shutdown")
async def stop_scheduler():
    """Stop the background scheduler when the app shuts down."""
    scheduler.shutdown()
    logger.info("Background scheduler stopped")

templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)

# Migration: Add grade column if it doesn't exist
def run_migrations():
    """Run database migrations for new columns."""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('players')]
    
    if 'grade' not in columns:
        with engine.connect() as conn:
            logger.info("Adding 'grade' column to players table...")
            conn.execute(text("ALTER TABLE players ADD COLUMN grade VARCHAR"))
            conn.commit()
            logger.info("Added 'grade' column to players table")

run_migrations()

# ---------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------
class PlayerUpdate(BaseModel):
    full_name: str
    birth_year: int | None
    jersey_number: int | None  # Allow None for jersey_number
    parent_email: str

class PlayerSportsUpdate(BaseModel):
    sports: List[str]

class DivisionUpdate(BaseModel):
    division: str

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

class BulkPlayerIds(BaseModel):
    player_ids: List[int]

class BulkRegistrationIds(BaseModel):
    registration_ids: List[int]

class SportsEngineSyncRequest(BaseModel):
    registration_id: str | None = None  # If None, sync all registrations

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
            logger.info(f"Created initial admin user: {email}")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
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
    try:
        logger.info(f"Login attempt for email: {email}")
        
        user = authenticate_user(db, email, password)
        if not user:
            logger.warning(f"Failed login attempt for: {email}")
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid credentials"},
                status_code=400
            )
        
        # Set session
        request.session["user_id"] = user.id
        logger.info(f"User {email} logged in successfully")
        
        # Use 303 status code for better mobile browser compatibility
        return RedirectResponse("/admin", status_code=303)
        
    except Exception as e:
        logger.error(f"Login error for {email}: {str(e)}", exc_info=True)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Server error. Please try again."},
            status_code=500
        )

@app.get("/logout")
def logout(request: Request):
    try:
        request.session.clear()
        logger.info("User logged out successfully")
    except Exception as e:
        logger.error(f"Logout error: {e}")
    return RedirectResponse("/login", status_code=303)

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
    logger.info(f"New user created: {email}")
    return RedirectResponse("/admin", status_code=303)

# ---------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
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

    # ------------------- BIRTH YEAR VIEW -------------------
    players_by_birth_year = defaultdict(list)
    waiting_room_players = []
    
    for p in players:
        sports = sorted({(r.sport or "").strip().lower() for r in p.registrations if r.sport})
        confirmation_sent = any(r.confirmation_sent for r in p.registrations)
        reg_id = p.registrations[0].id if p.registrations else None
        divisions = {(r.division or "").strip() for r in p.registrations if r.division}

        # Check if player is in Waiting Room OR is orphaned (no registrations, no birth year)
        is_orphaned = not p.registrations or not p.birth_year
        is_in_waiting_room = "Waiting Room" in divisions
        
        if is_in_waiting_room or is_orphaned:
            player_data = {
                "id": p.id,
                "registration_id": reg_id,
                "full_name": p.full_name,
                "birth_year": p.birth_year,
                "grade": p.grade,
                "parent_email": p.parent_email,
                "jersey_number": p.jersey_number,
                "sports": sports,
                "division": "Waiting Room",
                "confirmation_sent": confirmation_sent,
                "is_duplicate": p.id in duplicate_ids,
            }
            waiting_room_players.append(player_data)
            continue

        player_data = {
            "id": p.id,
            "registration_id": reg_id,
            "full_name": p.full_name,
            "birth_year": p.birth_year,
            "grade": p.grade,
            "parent_email": p.parent_email,
            "jersey_number": p.jersey_number,
            "sports": sports,
            "division": (p.registrations[0].division if p.registrations else ""),
            "confirmation_sent": confirmation_sent,
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
    
    # Validate required fields
    if not payload.full_name or not payload.parent_email:
        raise HTTPException(status_code=400, detail="Name and email are required")
    
    # If birth year is being set for the first time and they don't have a jersey, assign one
    if payload.birth_year and not player.birth_year and not player.jersey_number:
        from .services.assign import assign_jersey_number
        player.jersey_number = assign_jersey_number(db, payload.birth_year)
    elif payload.jersey_number is not None:
        # Only update jersey number if a value was explicitly provided
        player.jersey_number = payload.jersey_number
    
    player.full_name = payload.full_name
    player.birth_year = payload.birth_year
    player.parent_email = payload.parent_email
    
    db.commit()
    db.refresh(player)
    return {"status": "updated", "jersey_number": player.jersey_number}

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

# ---------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------
@app.post("/bulk/delete")
def bulk_delete_players(payload: BulkPlayerIds, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    deleted_count = 0
    failed_count = 0
    
    for player_id in payload.player_ids:
        try:
            player = db.query(Player).get(player_id)
            if player:
                db.delete(player)
                deleted_count += 1
            else:
                failed_count += 1
        except:
            failed_count += 1
    
    db.commit()
    return {"deleted": deleted_count, "failed": failed_count}

@app.post("/bulk/send-emails")
def bulk_send_emails(payload: BulkRegistrationIds, request: Request, db: Session = Depends(get_db)):
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    sent_count = 0
    failed_count = 0
    
    for reg_id in payload.registration_ids:
        try:
            reg = db.query(Registration).get(reg_id)
            if reg and not reg.confirmation_sent:
                # Reuse the existing send_registration_email logic
                parent_email = reg.player.parent_email
                player_info = {
                    "name": reg.player.full_name,
                    "jersey_number": reg.player.jersey_number,
                    "sport": reg.sport
                }
                
                if reg.division == "Pend Oreille Pines (High School Club Team)":
                    send_pines_confirmation_email(parent_email, [player_info], [reg], db)
                else:
                    from .email import PROMO_CODES
                    send_confirmation_email(parent_email, [player_info], PROMO_CODES.get(1), [reg], db)
                
                sent_count += 1
            else:
                failed_count += 1
        except:
            failed_count += 1
    
    return {"sent": sent_count, "failed": failed_count}

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
    
    player = reg.player
    old_division = reg.division
    new_division = normalize_division(payload.division, player.birth_year)
    
    # Update ALL registrations for this player to the same division
    all_player_regs = db.query(Registration).filter(Registration.player_id == player.id).all()
    for r in all_player_regs:
        r.division = new_division
    
    # ONLY assign a jersey number if moving OUT of Waiting Room AND player doesn't have one
    if old_division == "Waiting Room" and new_division != "Waiting Room":
        if not player.jersey_number:
            # Try to assign based on birth year first, if available
            if player.birth_year:
                new_jersey = assign_jersey_number(db, player.birth_year)
                logger.info(f"Assigned jersey #{new_jersey} to {player.full_name} based on birth year {player.birth_year}")
            else:
                # No birth year? Just assign the next available number across all players
                all_players = db.query(Player).all()
                taken = {p.jersey_number for p in all_players if p.jersey_number}
                new_jersey = 1
                while new_jersey in taken:
                    new_jersey += 1
                logger.info(f"Assigned jersey #{new_jersey} to {player.full_name} (no birth year available)")
            
            player.jersey_number = new_jersey
    
    db.commit()
    db.refresh(reg)
    return {
        "division": reg.division,
        "jersey_number": player.jersey_number
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
            # REMOVED: .filter(Registration.confirmation_sent == False)
            .all()
        )
    else:
        # No order number means this was manually added, always send it
        all_regs = [reg]
    
    if not all_regs:
        return {"status": "no registrations found"}
    
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
# Email Webhook (Legacy - for Blue Sombrero compatibility)
# ---------------------------------------------------------------------
@app.post("/email/receive")
async def receive_email(request: Request, db: Session = Depends(get_db)):
    """Receive inbound emails from SendGrid or similar service."""
    try:
        body = await request.body()
        email_text = body.decode('utf-8')
        
        # Save for debugging in development
        if os.getenv("ENV") != "production":
            save_inbound_email(email_text)
        
        # Process the email
        process_inbound_email(email_text, db)
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing inbound email: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------------------
# SportsEngine Integration
# ---------------------------------------------------------------------
@app.post("/sportsengine/sync")
def sportsengine_sync(
    payload: SportsEngineSyncRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Sync registrations from SportsEngine.
    
    If registration_id is provided, sync only that registration.
    Otherwise, sync all registrations with results.
    """
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    try:
        from .services.sportsengine import sync_registration, sync_all_registrations
        
        if payload.registration_id:
            result = sync_registration(payload.registration_id, db)
            logger.info(f"SportsEngine sync completed: {result}")
            return {
                "status": "success",
                "registration_id": payload.registration_id,
                **result
            }
        else:
            result = sync_all_registrations(db)
            logger.info(f"SportsEngine full sync completed: {result}")
            return {
                "status": "success",
                **result
            }
    except Exception as e:
        logger.error(f"SportsEngine sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sportsengine/registrations")
def sportsengine_list_registrations(request: Request, db: Session = Depends(get_db)):
    """
    List all registrations from SportsEngine.
    Returns registration IDs, names, and result counts.
    """
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    try:
        from .services.sportsengine import get_all_registrations
        
        registrations = get_all_registrations()
        return {
            "status": "success",
            "registrations": registrations
        }
    except Exception as e:
        logger.error(f"SportsEngine list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sportsengine/webhook")
async def sportsengine_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive webhook notifications from SportsEngine.
    
    Webhook payload format:
    {
        "organizationId": 12345,
        "resourceOperation": "create" | "update" | "delete",
        "resourceId": "uuid",
        "resourceType": "event" | "registration" | "profile" | etc.
    }
    """
    try:
        payload = await request.json()
        logger.info(f"Received SportsEngine webhook: {payload}")
        
        from .services.sportsengine import process_webhook
        result = process_webhook(payload, db)
        
        return {"status": "received", **result}
    except Exception as e:
        logger.error(f"SportsEngine webhook error: {e}", exc_info=True)
        # Return 200 to prevent SportsEngine from disabling webhooks
        return {"status": "error", "message": str(e)}


@app.get("/sportsengine", response_class=HTMLResponse)
def sportsengine_settings_page(request: Request, db: Session = Depends(get_db)):
    """SportsEngine integration settings page."""
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    
    return templates.TemplateResponse("sportsengine.html", {"request": request})


@app.get("/sportsengine/status")
def sportsengine_status(request: Request):
    """Check SportsEngine integration status and configuration."""
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    client_id = os.getenv("SPORTSENGINE_CLIENT_ID")
    client_secret = os.getenv("SPORTSENGINE_CLIENT_SECRET")
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    
    configured = bool(client_id and client_secret and org_id)
    
    status = {
        "configured": configured,
        "client_id_set": bool(client_id),
        "client_secret_set": bool(client_secret),
        "org_id_set": bool(org_id),
        "org_id": org_id if org_id else None
    }
    
    # Try to authenticate if configured
    if configured:
        try:
            from .services.sportsengine import get_access_token
            get_access_token()
            status["authenticated"] = True
        except Exception as e:
            status["authenticated"] = False
            status["auth_error"] = str(e)
    
    return status


@app.get("/debug/find-player/{name}")
def debug_find_player(name: str, request: Request, db: Session = Depends(get_db)):
    """Debug endpoint to find a player by name, including those without registrations."""
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    from sqlalchemy import func
    
    # Search for player (case-insensitive partial match)
    players = db.query(Player).filter(
        func.lower(Player.full_name).contains(name.lower())
    ).all()
    
    results = []
    for p in players:
        regs = db.query(Registration).filter(Registration.player_id == p.id).all()
        results.append({
            "id": p.id,
            "full_name": p.full_name,
            "birth_year": p.birth_year,
            "jersey_number": p.jersey_number,
            "parent_email": p.parent_email,
            "locked": p.locked,
            "registrations": [
                {
                    "id": r.id,
                    "sport": r.sport,
                    "season": r.season,
                    "division": r.division,
                    "confirmation_sent": r.confirmation_sent
                }
                for r in regs
            ]
        })
    
    return {"search": name, "found": len(results), "players": results}


@app.delete("/debug/delete-player/{player_id}")
def debug_delete_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a player by ID (including orphaned players not visible in admin)."""
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    name = player.full_name
    
    # Delete registrations first
    db.query(Registration).filter(Registration.player_id == player_id).delete()
    db.delete(player)
    db.commit()
    
    return {"deleted": True, "player_id": player_id, "name": name}


@app.post("/debug/fix-player/{player_id}")
def debug_fix_player(player_id: int, birth_year: int, request: Request, db: Session = Depends(get_db)):
    """Fix a player's birth year and assign a jersey number."""
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    from .services.assign import assign_jersey_number
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    player.birth_year = birth_year
    
    if not player.jersey_number:
        player.jersey_number = assign_jersey_number(db, birth_year)
    
    db.commit()
    
    return {
        "fixed": True,
        "player_id": player_id,
        "name": player.full_name,
        "birth_year": player.birth_year,
        "jersey_number": player.jersey_number
    }


@app.post("/debug/mark-all-sent")
def debug_mark_all_sent(request: Request, db: Session = Depends(get_db)):
    """Mark all registrations as confirmation_sent=True without sending emails."""
    try:
        require_login(request)
    except HTTPException as exc:
        raise exc
    
    count = db.query(Registration).filter(Registration.confirmation_sent == False).update(
        {Registration.confirmation_sent: True}
    )
    db.commit()
    
    return {"marked_as_sent": count}

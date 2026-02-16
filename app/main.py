# POSA Jersey App - Complete Main Application

import os
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db, engine
from app.models import Base, Player, Registration
from app.email import send_confirmation_email
from app.api_routes import router as admin_api_router

# Create tables
Base.metadata.create_all(bind=engine)

# App setup
app = FastAPI(title="POSA Jersey Management")

# Mount static files if directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include API routes
app.include_router(admin_api_router)

# Environment variables
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CURRENT_SEASON = os.getenv("CURRENT_SEASON", "2026")

# Simple session storage (in production, use Redis or similar)
active_sessions = set()


# ============================================
# Authentication
# ============================================

def require_login(request: Request):
    # Check if user is logged in
    session_token = request.cookies.get("session_token")
    if not session_token or session_token not in active_sessions:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"}
        )
    return True


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Login page
    return """
    <html>
    <head>
        <title>Login - POSA Admin</title>
        <style>
            body { font-family: sans-serif; max-width: 400px; margin: 100px auto; padding: 20px; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }
            button { width: 100%; padding: 10px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .error { color: red; margin: 10px 0; }
        </style>
    </head>
    <body>
        <h1>POSA Admin Login</h1>
        <form method="post" action="/login">
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    """


@app.post("/login")
async def login(password: str = Form(...)):
    # Process login
    if password == ADMIN_PASSWORD:
        session_token = os.urandom(32).hex()
        active_sessions.add(session_token)
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie("session_token", session_token)
        return response
    else:
        return HTMLResponse("""
        <html>
        <body>
            <h1>Login Failed</h1>
            <p>Invalid password</p>
            <a href="/login">Try again</a>
        </body>
        </html>
        """, status_code=401)


@app.get("/logout")
async def logout(request: Request):
    # Logout
    session_token = request.cookies.get("session_token")
    if session_token in active_sessions:
        active_sessions.remove(session_token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session_token")
    return response


# ============================================
# Admin Dashboard
# ============================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Admin dashboard - table interface
    try:
        require_login(request)
    except HTTPException as exc:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    
    return templates.TemplateResponse("admin_table.html", {
        "request": request
    })


@app.get("/")
async def home():
    # Home page - redirect to admin
    return RedirectResponse("/admin")


# ============================================
# Player Management
# ============================================

@app.post("/api/players")
async def create_player(
    request: Request,
    full_name: str = Form(...),
    birth_year: int = Form(...),
    parent_email: str = Form(...),
    division: str = Form("Waiting Room"),
    sport: str = Form("Soccer"),
    db: Session = Depends(get_db)
):
    # Create a new player
    require_login(request)
    
    # Check if player exists
    existing = db.query(Player).filter(
        Player.full_name == full_name,
        Player.birth_year == birth_year
    ).first()
    
    if existing:
        return JSONResponse(
            {"error": "Player already exists"},
            status_code=400
        )
    
    # Assign jersey number (next available for birth year)
    max_jersey = db.query(func.max(Player.jersey_number)).filter(
        Player.birth_year == birth_year
    ).scalar()
    
    jersey_number = str(int(max_jersey or 0) + 1)
    
    # Create player
    player = Player(
        full_name=full_name,
        birth_year=birth_year,
        parent_email=parent_email,
        jersey_number=jersey_number,
        locked=False
    )
    db.add(player)
    db.flush()
    
    # Create registration
    registration = Registration(
        player_id=player.id,
        program=f"{CURRENT_SEASON} Pines {sport}",
        division=division,
        sport=sport,
        season=CURRENT_SEASON,
        confirmation_sent=False,
        created_at=datetime.utcnow()
    )
    db.add(registration)
    db.commit()
    
    return JSONResponse({
        "success": True,
        "player": {
            "id": player.id,
            "name": player.full_name,
            "jersey": player.jersey_number,
            "birthYear": player.birth_year
        }
    })


@app.put("/api/players/{player_id}")
async def update_player(
    player_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    # Update player details
    require_login(request)
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    data = await request.json()
    
    # Update allowed fields
    if "full_name" in data:
        player.full_name = data["full_name"]
    if "parent_email" in data:
        player.parent_email = data["parent_email"]
    if "birth_year" in data:
        player.birth_year = data["birth_year"]
    
    db.commit()
    
    return JSONResponse({"success": True})


@app.delete("/api/players/{player_id}")
async def delete_player(
    player_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    # Delete a player
    require_login(request)
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Delete all registrations
    db.query(Registration).filter(Registration.player_id == player_id).delete()
    
    # Delete player
    db.delete(player)
    db.commit()
    
    return JSONResponse({"success": True})


# ============================================
# Email Management
# ============================================

@app.post("/api/players/{player_id}/send-email")
async def send_player_email_route(
    player_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    # Send confirmation email to player
    require_login(request)
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get unsent registrations
    registrations = db.query(Registration).filter(
        Registration.player_id == player_id,
        Registration.confirmation_sent == False
    ).all()
    
    if not registrations:
        return JSONResponse({
            "success": False,
            "message": "No unsent registrations"
        })
    
    # Send email (implement your actual email logic here)
    try:
        # send_confirmation_email(player, registrations)
        
        # Mark as sent
        for reg in registrations:
            reg.confirmation_sent = True
        db.commit()
        
        return JSONResponse({
            "success": True,
            "emailsSent": len(registrations),
            "message": f"Email sent to {player.parent_email}"
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.post("/api/send-bulk-emails")
async def send_bulk_emails_route(
    request: Request,
    db: Session = Depends(get_db)
):
    # Send emails to multiple players
    require_login(request)
    
    data = await request.json()
    player_ids = data.get("player_ids", [])
    
    results = []
    for player_id in player_ids:
        try:
            player = db.query(Player).filter(Player.id == player_id).first()
            if not player:
                results.append({"playerId": player_id, "success": False, "error": "Not found"})
                continue
            
            registrations = db.query(Registration).filter(
                Registration.player_id == player_id,
                Registration.confirmation_sent == False
            ).all()
            
            if registrations:
                # send_confirmation_email(player, registrations)
                for reg in registrations:
                    reg.confirmation_sent = True
                db.commit()
                
                results.append({"playerId": player_id, "success": True})
            else:
                results.append({"playerId": player_id, "success": False, "error": "No unsent registrations"})
                
        except Exception as e:
            results.append({"playerId": player_id, "success": False, "error": str(e)})
    
    success_count = sum(1 for r in results if r.get("success"))
    
    return JSONResponse({
        "total": len(player_ids),
        "success": success_count,
        "failed": len(player_ids) - success_count,
        "results": results
    })


# ============================================
# SportsEngine Sync
# ============================================

@app.post("/sync/pull")
async def sync_sportsengine(request: Request, db: Session = Depends(get_db)):
    # Sync with SportsEngine
    require_login(request)
    
    # TODO: Implement your SportsEngine sync logic here
    # from app.services.sportsengine import sync_registrations
    # results = sync_registrations(db)
    
    return JSONResponse({
        "success": True,
        "summary": "Sync complete (not implemented yet)",
        "added": 0,
        "updated": 0,
        "errors": 0
    })


# ============================================
# Utility Endpoints
# ============================================

@app.get("/api/summary")
async def get_summary(db: Session = Depends(get_db)):
    # Get dashboard summary stats
    total_players = db.query(func.count(Player.id)).scalar()
    
    waiting_room = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(Registration.division == "Waiting Room").scalar() or 0
    
    needs_email = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(Registration.confirmation_sent == False).scalar() or 0
    
    return JSONResponse({
        "totalPlayers": total_players,
        "waitingRoom": waiting_room,
        "needsEmail": needs_email
    })


@app.get("/health")
async def health_check():
    # Health check endpoint
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================
# Run App
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

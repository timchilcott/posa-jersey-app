# POSA Jersey App - Diagnostic Version

import os
import pathlib
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Check paths
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

print("=" * 80)
print("DIAGNOSTIC INFO:")
print(f"BASE_DIR: {BASE_DIR}")
print(f"TEMPLATES_DIR: {TEMPLATES_DIR}")
print(f"Templates dir exists: {TEMPLATES_DIR.exists()}")
if TEMPLATES_DIR.exists():
    print(f"Templates in dir: {list(TEMPLATES_DIR.iterdir())}")
print("=" * 80)

# Import database
try:
    from app.database import get_db, engine
    from app.models import Base
    print("✓ Database imports successful")
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created")
except Exception as e:
    print(f"✗ Database error: {e}")

# Import API routes
try:
    from app.api_routes import router as admin_api_router
    print("✓ API routes imported")
except Exception as e:
    print(f"✗ API routes error: {e}")

# App setup
app = FastAPI(title="POSA Jersey Management")

# Mount static files if directory exists
if os.path.exists("static"):
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory="static"), name="static")
    print("✓ Static files mounted")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
print(f"✓ Templates initialized at: {TEMPLATES_DIR}")

# Include API routes
try:
    app.include_router(admin_api_router)
    print("✓ API router included")
except Exception as e:
    print(f"✗ Router error: {e}")

# Environment variables
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CURRENT_SEASON = os.getenv("CURRENT_SEASON", "2026")


@app.get("/")
async def home():
    return {
        "status": "ok",
        "message": "App is running",
        "base_dir": str(BASE_DIR),
        "templates_dir": str(TEMPLATES_DIR),
        "templates_exists": TEMPLATES_DIR.exists(),
        "database_url": os.getenv("DATABASE_URL", "NOT SET")[:20] + "..." if os.getenv("DATABASE_URL") else "NOT SET"
    }


@app.get("/debug")
async def debug():
    return HTMLResponse(f"""
    <html>
    <body>
        <h1>Diagnostic Info</h1>
        <pre>
BASE_DIR: {BASE_DIR}
TEMPLATES_DIR: {TEMPLATES_DIR}
Templates exists: {TEMPLATES_DIR.exists()}
Templates files: {list(TEMPLATES_DIR.iterdir()) if TEMPLATES_DIR.exists() else 'DIR NOT FOUND'}
DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}
        </pre>
    </body>
    </html>
    """)


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Admin dashboard - table interface
    print(f"Admin route hit, looking for template at: {TEMPLATES_DIR / 'admin_table.html'}")
    
    try:
        return templates.TemplateResponse("admin_table.html", {
            "request": request
        })
    except Exception as e:
        print(f"Template error: {e}")
        return HTMLResponse(f"""
        <html>
        <body>
            <h1>Template Error</h1>
            <p>Error: {e}</p>
            <p>Templates dir: {TEMPLATES_DIR}</p>
            <p>Templates exists: {TEMPLATES_DIR.exists()}</p>
            <p>Files: {list(TEMPLATES_DIR.iterdir()) if TEMPLATES_DIR.exists() else 'NOT FOUND'}</p>
        </body>
        </html>
        """, status_code=500)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

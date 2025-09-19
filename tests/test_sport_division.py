import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure DATABASE_URL and CURRENT_SEASON set before importing application modules
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['CURRENT_SEASON'] = '2024'

from fastapi.testclient import TestClient
import app.main as app_main
from app.main import app, Base, get_db
from app.models import Sport, Division


@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # bypass authentication and startup logic
    app_main.require_login = lambda request: None
    app.router.on_startup.clear()

    with TestClient(app) as c:
        c.SessionLocal = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def test_db(client):
    """Get a database session for testing."""
    return client.SessionLocal()


def test_create_sport_success(client, test_db):
    """Test successful sport creation."""
    sport_data = {
        "name": "tennis",
        "display_name": "Tennis"
    }
    
    response = client.post("/sports", json=sport_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "tennis"
    assert data["display_name"] == "Tennis"
    assert "id" in data
    
    # Verify in database
    sport = test_db.query(Sport).filter(Sport.name == "tennis").first()
    assert sport is not None
    assert sport.display_name == "Tennis"


def test_create_sport_duplicate(client, test_db):
    """Test creating duplicate sport returns error."""
    # Create first sport
    sport = Sport(name="hockey", display_name="Hockey")
    test_db.add(sport)
    test_db.commit()
    
    # Try to create duplicate
    sport_data = {
        "name": "hockey",
        "display_name": "Ice Hockey"
    }
    
    response = client.post("/sports", json=sport_data)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_create_division_success(client, test_db):
    """Test successful division creation."""
    # Create sport first
    sport = Sport(name="football", display_name="Football")
    test_db.add(sport)
    test_db.commit()
    test_db.refresh(sport)
    
    division_data = {
        "name": "U16",
        "display_name": "Under 16",
        "sport_id": sport.id,
        "sort_order": 7
    }
    
    response = client.post("/divisions", json=division_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "U16"
    assert data["display_name"] == "Under 16"
    assert data["sport_id"] == sport.id
    assert data["sort_order"] == 7
    
    # Verify in database
    division = test_db.query(Division).filter(Division.name == "U16").first()
    assert division is not None
    assert division.sport_id == sport.id


def test_create_division_sport_not_found(client, test_db):
    """Test creating division for non-existent sport returns error."""
    division_data = {
        "name": "U16",
        "display_name": "Under 16",
        "sport_id": 999,
        "sort_order": 7
    }
    
    response = client.post("/divisions", json=division_data)
    assert response.status_code == 404
    assert "Sport not found" in response.json()["detail"]


def test_create_division_duplicate(client, test_db):
    """Test creating duplicate division for same sport returns error."""
    # Create sport and division
    sport = Sport(name="rugby", display_name="Rugby")
    test_db.add(sport)
    test_db.commit()
    test_db.refresh(sport)
    
    division = Division(name="U18", display_name="Under 18", sport_id=sport.id)
    test_db.add(division)
    test_db.commit()
    
    # Try to create duplicate
    division_data = {
        "name": "U18",
        "display_name": "Under Eighteen",
        "sport_id": sport.id,
        "sort_order": 8
    }
    
    response = client.post("/divisions", json=division_data)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_get_sports_with_divisions(client, test_db):
    """Test getting all sports with their divisions."""
    # Create sports and divisions
    sport1 = Sport(name="lacrosse", display_name="Lacrosse")
    sport2 = Sport(name="swimming", display_name="Swimming")
    test_db.add_all([sport1, sport2])
    test_db.commit()
    test_db.refresh(sport1)
    test_db.refresh(sport2)
    
    div1 = Division(name="U10", display_name="Under 10", sport_id=sport1.id, sort_order=1)
    div2 = Division(name="U12", display_name="Under 12", sport_id=sport1.id, sort_order=2)
    div3 = Division(name="Beginner", display_name="Beginner", sport_id=sport2.id, sort_order=0)
    test_db.add_all([div1, div2, div3])
    test_db.commit()
    
    response = client.get("/sports")
    assert response.status_code == 200
    
    sports = response.json()
    assert len(sports) == 2
    
    # Find lacrosse sport
    lacrosse_sport = next(s for s in sports if s["name"] == "lacrosse")
    assert lacrosse_sport["display_name"] == "Lacrosse"
    assert len(lacrosse_sport["divisions"]) == 2
    
    # Check divisions are sorted by sort_order
    divisions = lacrosse_sport["divisions"]
    assert divisions[0]["name"] == "U10"
    assert divisions[1]["name"] == "U12"
    
    # Find swimming sport
    swimming_sport = next(s for s in sports if s["name"] == "swimming")
    assert len(swimming_sport["divisions"]) == 1
    assert swimming_sport["divisions"][0]["name"] == "Beginner"


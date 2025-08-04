import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure DATABASE_URL set before importing application modules
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from fastapi.testclient import TestClient
import app.main as app_main
from app.main import app, Base, get_db
from app.models import Player, Registration
from app.email import normalize_division


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


def setup_players_unassigned(SessionLocal):
    db = SessionLocal()
    p1 = Player(full_name='Assigned', parent_email='a@example.com', jersey_number=1)
    db.add(p1)
    db.flush()
    db.add(Registration(player_id=p1.id, program='prog', division='U8', sport='soccer', season='2024'))
    p2 = Player(full_name='Blank', parent_email='b@example.com', jersey_number=2)
    db.add(p2)
    db.flush()
    db.add(Registration(player_id=p2.id, program='prog', division='', sport='soccer', season='2024'))
    p3 = Player(full_name='Mystery', parent_email='c@example.com', jersey_number=3)
    db.add(p3)
    db.flush()
    db.add(Registration(player_id=p3.id, program='prog', division='Unknown', sport='soccer', season='2024'))
    db.commit()
    db.close()


def setup_player(SessionLocal):
    db = SessionLocal()
    p1 = Player(full_name='Player1', parent_email='p1@example.com', jersey_number=4)
    db.add(p1)
    db.flush()
    reg = Registration(player_id=p1.id, program='prog', division='U8', sport='soccer', season='2024')
    db.add(reg)
    db.commit()
    reg_id = reg.id
    db.close()
    return reg_id


def test_normalize_pend_oreille():
    assert normalize_division('Pend Oreille Pines (High School Club Team)') == 'Pend Oreille Pines (High School Club Team)'


def test_admin_unassigned_tab(client):
    setup_players_unassigned(client.SessionLocal)
    response = client.get('/admin')
    assert response.status_code == 200
    text = response.text
    assert 'Unassigned' in text
    assert 'Unknown' not in text
    assert 'Blank' in text
    assert 'Mystery' in text
    assert 'Pend Oreille Pines (High School Club Team)' in text


def test_move_player_to_pines_division(client):
    reg_id = setup_player(client.SessionLocal)
    response = client.put(f'/registrations/{reg_id}/division', json={'division': 'Pend Oreille Pines (High School Club Team)'})
    assert response.status_code == 200
    data = response.json()
    assert data['division'] == 'Pend Oreille Pines (High School Club Team)'
    db = client.SessionLocal()
    reg = db.query(Registration).get(reg_id)
    assert reg.division == 'Pend Oreille Pines (High School Club Team)'
    db.close()

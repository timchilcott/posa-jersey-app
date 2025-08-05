import os
import re
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
from app.models import Player, Registration


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


def test_admin_player_count(client):
    db = client.SessionLocal()
    p1 = Player(full_name='Registered', parent_email='r@example.com', jersey_number=1)
    db.add(p1)
    db.flush()
    db.add(Registration(player_id=p1.id, program='prog', division='U8', sport='soccer', season='2024'))
    p2 = Player(full_name='Unregistered', parent_email='u@example.com', jersey_number=2)
    db.add(p2)
    db.commit()
    db.close()

    response = client.get('/admin')
    assert response.status_code == 200
    match = re.search(r'fs-4 fw-bold text-dark">(\d+)</div>\s*<small class="text-muted">Total Athletes</small>', response.text)
    assert match is not None
    assert match.group(1) == '1'


def test_admin_excludes_unassigned_divisions(client):
    db = client.SessionLocal()
    # Player with valid division
    p_valid = Player(full_name='Valid', parent_email='v@example.com', jersey_number=1)
    db.add(p_valid)
    db.flush()
    db.add(Registration(player_id=p_valid.id, program='prog', division='U8', sport='soccer', season='2024'))

    # Player with only excluded division
    p_blank = Player(full_name='Blank', parent_email='b@example.com', jersey_number=2)
    db.add(p_blank)
    db.flush()
    db.add(Registration(player_id=p_blank.id, program='prog', division='', sport='soccer', season='2024'))

    # Player with mixed divisions (one excluded, one valid)
    p_mixed = Player(full_name='Mixed', parent_email='m@example.com', jersey_number=3)
    db.add(p_mixed)
    db.flush()
    db.add(Registration(player_id=p_mixed.id, program='prog', division='Unknown', sport='basketball', season='2024'))
    db.add(Registration(player_id=p_mixed.id, program='prog', division='U10', sport='soccer', season='2024'))

    db.commit()
    db.close()

    response = client.get('/admin')
    assert response.status_code == 200
    match = re.search(r'fs-4 fw-bold text-dark">(\d+)</div>\s*<small class="text-muted">Total Athletes</small>', response.text)
    assert match is not None
    # Only p_valid and p_mixed should be counted
    assert match.group(1) == '2'

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

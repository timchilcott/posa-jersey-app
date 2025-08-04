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


def setup_players(SessionLocal):
    db = SessionLocal()
    # Player to move from U8
    p1 = Player(full_name='Player1', parent_email='p1@example.com', jersey_number=1)
    db.add(p1)
    db.flush()
    reg1 = Registration(player_id=p1.id, program='prog', division='U8', sport='soccer', season='2024')
    db.add(reg1)
    # existing players in target division taking jersey numbers 1 and 2
    for num in [1, 2]:
        px = Player(full_name=f'P{num}', parent_email=f'p{num}@ex.com', jersey_number=num)
        db.add(px)
        db.flush()
        db.add(Registration(player_id=px.id, program='prog', division='U10', sport='soccer', season='2024'))
    db.commit()
    reg_id = reg1.id
    db.close()
    return reg_id


def test_move_player_between_divisions(client):
    reg_id = setup_players(client.SessionLocal)

    response = client.put(f"/registrations/{reg_id}/division", json={'division': 'U10'})
    assert response.status_code == 200
    data = response.json()
    assert data['division'] == 'U10'
    assert data['jersey_number'] == 3

    db = client.SessionLocal()
    reg = db.query(Registration).get(reg_id)
    assert reg.division == 'U10'
    assert reg.player.jersey_number == 3
    db.close()

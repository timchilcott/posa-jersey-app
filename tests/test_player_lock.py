import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['CURRENT_SEASON'] = '2024'

from fastapi.testclient import TestClient
import app.main as app_main
from app.main import app, Base, get_db
from app.models import Player


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
    app_main.require_login = lambda request: None
    app.router.on_startup.clear()

    with TestClient(app) as c:
        c.SessionLocal = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()


def test_lock_unlock_player(client):
    db = client.SessionLocal()
    player = Player(full_name='Test', parent_email='t@example.com', jersey_number=10)
    db.add(player)
    db.commit()
    db.refresh(player)
    db.close()

    response = client.put(f"/players/{player.id}/lock", json={"locked": True})
    assert response.status_code == 200
    assert response.json()["locked"] is True

    db = client.SessionLocal()
    assert db.get(Player, player.id).locked is True
    db.close()

    response = client.put(f"/players/{player.id}/lock", json={"locked": False})
    assert response.status_code == 200
    db = client.SessionLocal()
    assert db.get(Player, player.id).locked is False
    db.close()

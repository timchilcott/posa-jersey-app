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
from app.models import Player, Registration
from app.email import PROMO_CODES


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


def test_group_registration_email(client, monkeypatch):
    db = client.SessionLocal()
    p1 = Player(full_name='Alex', parent_email='parent@example.com', jersey_number=12)
    p2 = Player(full_name='Jamie', parent_email='parent@example.com', jersey_number=34)
    db.add_all([p1, p2])
    db.flush()
    r1 = Registration(player_id=p1.id, program='prog', division='U8', sport='soccer', season='2024', confirmation_sent=False)
    r2 = Registration(player_id=p2.id, program='prog', division='U10', sport='soccer', season='2024', confirmation_sent=False)
    db.add_all([r1, r2])
    db.commit()
    r1_id, r2_id = r1.id, r2.id
    db.close()

    captured = {}

    def fake_send_confirmation_email(to_email, players, order_url, registrations=None, db=None, promo_code=None):
        captured['to_email'] = to_email
        captured['players'] = players
        captured['promo_code'] = promo_code
        if registrations and db:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()

    monkeypatch.setattr(app_main, 'send_confirmation_email', fake_send_confirmation_email)

    response = client.post(f'/registrations/{r1_id}/send_email')
    assert response.status_code == 200
    assert captured['to_email'] == 'parent@example.com'
    assert len(captured['players']) == 2
    assert captured['promo_code'] == PROMO_CODES.get(2)

    db = client.SessionLocal()
    assert db.query(Registration).get(r1_id).confirmation_sent
    assert db.query(Registration).get(r2_id).confirmation_sent
    db.close()

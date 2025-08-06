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
    app_main.require_login = lambda request: None
    app.router.on_startup.clear()

    with TestClient(app) as c:
        c.SessionLocal = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()


def test_high_school_email_no_promo(client, monkeypatch):
    db = client.SessionLocal()
    p = Player(full_name='HS Player', parent_email='parent@example.com', jersey_number=9)
    db.add(p)
    db.flush()
    r = Registration(player_id=p.id, program='prog', division='Pend Oreille Pines (High School Club Team)', sport='soccer', season='2024', confirmation_sent=False)
    db.add(r)
    db.commit()
    reg_id = r.id
    db.close()

    captured = {}

    def fake_pines_email(to_email, players, registrations=None, db=None):
        captured['to_email'] = to_email
        captured['players'] = players
        if registrations and db:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()

    monkeypatch.setattr(app_main, 'send_pines_confirmation_email', fake_pines_email)
    # ensure standard email not called
    monkeypatch.setattr(app_main, 'send_confirmation_email', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('standard email should not be sent')))

    response = client.post(f'/registrations/{reg_id}/send_email')
    assert response.status_code == 200
    assert captured['to_email'] == 'parent@example.com'
    assert len(captured['players']) == 1
    assert 'promo_code' not in captured['players'][0]

    db = client.SessionLocal()
    assert db.query(Registration).get(reg_id).confirmation_sent
    db.close()


def test_mixed_family_two_emails(client, monkeypatch):
    db = client.SessionLocal()
    # regular player
    p_reg = Player(full_name='Youth', parent_email='parent@example.com', jersey_number=10)
    # high school player
    p_hs = Player(full_name='HS', parent_email='parent@example.com', jersey_number=1)
    db.add_all([p_reg, p_hs])
    db.flush()
    r_reg = Registration(player_id=p_reg.id, program='prog', division='U10', sport='soccer', season='2024', confirmation_sent=False)
    r_hs = Registration(player_id=p_hs.id, program='prog', division='Pend Oreille Pines (High School Club Team)', sport='soccer', season='2024', confirmation_sent=False)
    db.add_all([r_reg, r_hs])
    db.commit()
    r_reg_id, r_hs_id = r_reg.id, r_hs.id
    db.close()

    captured = {'standard': None, 'pines': None}

    def fake_standard_email(to_email, players, promo_code=None, registrations=None, db=None):
        captured['standard'] = {'to_email': to_email, 'players': players, 'promo_code': promo_code}
        if registrations and db:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()

    def fake_pines_email(to_email, players, registrations=None, db=None):
        captured['pines'] = {'to_email': to_email, 'players': players}
        if registrations and db:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()

    monkeypatch.setattr(app_main, 'send_confirmation_email', fake_standard_email)
    monkeypatch.setattr(app_main, 'send_pines_confirmation_email', fake_pines_email)

    response = client.post(f'/registrations/{r_reg_id}/send_email')
    assert response.status_code == 200
    assert captured['standard'] is not None
    assert captured['pines'] is not None

    assert captured['standard']['promo_code'] == PROMO_CODES.get(1)
    assert len(captured['standard']['players']) == 1
    assert len(captured['pines']['players']) == 1
    assert 'promo_code' not in captured['pines']['players'][0]

    db = client.SessionLocal()
    assert db.query(Registration).get(r_reg_id).confirmation_sent
    assert db.query(Registration).get(r_hs_id).confirmation_sent
    db.close()

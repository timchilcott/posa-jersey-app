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

    def fake_send_confirmation_email(to_email, players, registrations=None, db=None):
        captured['to_email'] = to_email
        captured['players'] = players
        if registrations and db:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()

    monkeypatch.setattr(app_main, 'send_confirmation_email', fake_send_confirmation_email)

    response = client.post(f'/registrations/{r1_id}/send_email')
    assert response.status_code == 200
    assert captured['to_email'] == 'parent@example.com'
    assert len(captured['players']) == 2
    expected = PROMO_CODES.get(2)
    assert {p['promo_code'] for p in captured['players']} == {expected}
    assert {p['jersey_number'] for p in captured['players']} == {12, 34}

    db = client.SessionLocal()
    assert db.query(Registration).get(r1_id).confirmation_sent
    assert db.query(Registration).get(r2_id).confirmation_sent
    db.close()

def _mock_email(monkeypatch, captured):
    def fake_send_confirmation_email(to_email, players, registrations=None, db=None):
        body = "\n".join(
            f"{p['name']} (#{p['jersey_number']}) {p['promo_code']}" for p in players
        )
        captured['body'] = body
        if registrations and db:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    monkeypatch.setattr(app_main, 'send_confirmation_email', fake_send_confirmation_email)


def test_single_player_email_body(client, monkeypatch):
    db = client.SessionLocal()
    player = Player(full_name='Solo', parent_email='parent@example.com', jersey_number=7)
    db.add(player)
    db.flush()
    reg = Registration(player_id=player.id, program='prog', division='U6', sport='soccer', season='2024', confirmation_sent=False)
    db.add(reg)
    db.commit()
    reg_id = reg.id
    db.close()

    captured = {}
    _mock_email(monkeypatch, captured)

    response = client.post(f'/registrations/{reg_id}/send_email')
    assert response.status_code == 200

    body_lines = captured['body'].splitlines()
    promo = PROMO_CODES.get(1)
    assert len(body_lines) == 1
    assert 'Solo' in body_lines[0]
    assert promo in body_lines[0]
    assert '#7' in body_lines[0]

    db = client.SessionLocal()
    assert db.query(Registration).get(reg_id).confirmation_sent
    db.close()


def test_three_player_email_body(client, monkeypatch):
    db = client.SessionLocal()
    names = ['Alex', 'Jamie', 'Taylor']
    regs = []
    for idx, name in enumerate(names, start=1):
        p = Player(full_name=name, parent_email='parent@example.com', jersey_number=10 * idx)
        db.add(p)
        db.flush()
        r = Registration(player_id=p.id, program='prog', division='U8', sport='soccer', season='2024', confirmation_sent=False)
        db.add(r)
        regs.append(r)
    db.commit()
    reg_ids = [r.id for r in regs]
    db.close()

    captured = {}
    _mock_email(monkeypatch, captured)

    response = client.post(f'/registrations/{reg_ids[0]}/send_email')
    assert response.status_code == 200

    body_lines = captured['body'].splitlines()
    promo = PROMO_CODES.get(3)
    assert len(body_lines) == 3
    for name in names:
        assert any(name in line for line in body_lines)
    for line in body_lines:
        assert promo in line
    for num in [10, 20, 30]:
        assert any(f'#{num}' in line for line in body_lines)

    db = client.SessionLocal()
    for rid in reg_ids:
        assert db.query(Registration).get(rid).confirmation_sent
    db.close()

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app.email as email_module
from app.api_routes import send_player_email
from app.database import Base
from app.models import Player, Registration
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _add_player_with_registration(db, *, is_high_school=False, division="U14"):
    player = Player(
        full_name="Test Player",
        parent_email="parent@example.com",
        jersey_number=9,
        is_high_school=is_high_school,
    )
    db.add(player)
    db.flush()
    registration = Registration(
        player_id=player.id,
        program="Soccer",
        division=division,
        sport="Soccer",
        season="Spring 2026",
        confirmation_sent=False,
    )
    db.add(registration)
    db.commit()
    return player.id


def test_regular_player_uses_standard_template(monkeypatch):
    db = _session()
    player_id = _add_player_with_registration(db)
    captured = {}

    def fake_standard_email(to_email, players, promo_code=None, registrations=None, db=None):
        captured["standard"] = {
            "to_email": to_email,
            "players": players,
            "promo_code": promo_code,
        }

    def fake_pines_email(*args, **kwargs):
        raise AssertionError("high school email should not be sent")

    monkeypatch.setattr(email_module, "send_confirmation_email", fake_standard_email)
    monkeypatch.setattr(email_module, "send_pines_confirmation_email", fake_pines_email)

    result = send_player_email(player_id, db=db)

    assert result["success"] is True
    assert captured["standard"]["to_email"] == "parent@example.com"
    assert captured["standard"]["players"][0]["name"] == "Test Player"
    db.close()


def test_high_school_flag_uses_high_school_template(monkeypatch):
    db = _session()
    player_id = _add_player_with_registration(db, is_high_school=True, division="U14")
    captured = {}

    def fake_standard_email(*args, **kwargs):
        raise AssertionError("standard email should not be sent")

    def fake_pines_email(to_email, players, registrations=None, db=None):
        captured["pines"] = {
            "to_email": to_email,
            "players": players,
            "registrations": registrations,
        }

    monkeypatch.setattr(email_module, "send_confirmation_email", fake_standard_email)
    monkeypatch.setattr(email_module, "send_pines_confirmation_email", fake_pines_email)

    result = send_player_email(player_id, db=db)

    assert result["success"] is True
    assert captured["pines"]["to_email"] == "parent@example.com"
    assert captured["pines"]["players"][0]["name"] == "Test Player"
    assert len(captured["pines"]["registrations"]) == 1
    db.close()

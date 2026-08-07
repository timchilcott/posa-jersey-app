import os
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.api_routes import create_player, get_filtered_players
from app.database import Base
from app.models import Player
from app.player_dates import (
    age_group_for_season,
    birth_year_from_date_of_birth,
    parse_date_of_birth,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_parse_date_of_birth_common_formats():
    assert parse_date_of_birth("2021-05-04") == date(2021, 5, 4)
    assert parse_date_of_birth("05/04/2021") == date(2021, 5, 4)
    assert birth_year_from_date_of_birth("2021-05-04") == 2021


def test_age_group_works_back_to_u4_and_u5():
    assert age_group_for_season("2023-04-01", 2026) == 4
    assert age_group_for_season("2022-04-01", 2026) == 5
    assert age_group_for_season("2021-04-01", 2026) == 6


def test_create_player_derives_birth_year_from_date_of_birth():
    db = _session()
    try:
        result = create_player(
            {
                "full_name": "DOB Player",
                "parent_email": "parent@example.com",
                "date_of_birth": "2021-05-04",
            },
            db=db,
        )
        player = db.query(Player).filter(Player.id == result["id"]).one()
        assert player.date_of_birth == date(2021, 5, 4)
        assert player.birth_year == 2021
    finally:
        db.close()


def test_admin_players_payload_includes_date_of_birth():
    db = _session()
    try:
        db.add(
            Player(
                full_name="Payload Player",
                parent_email="parent@example.com",
                date_of_birth=date(2020, 8, 9),
                birth_year=2020,
                jersey_number=7,
            )
        )
        db.commit()

        data = get_filtered_players(db=db)
        assert data["players"][0]["dateOfBirth"] == "2020-08-09"
        assert data["players"][0]["birthYear"] == 2020
    finally:
        db.close()

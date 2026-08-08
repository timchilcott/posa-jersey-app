import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Player, PlayerAlias
from app.player_aliases import find_player_by_alias, normalize_player_alias
from app.player_alias_sync import install_player_alias_sync_patch
from app.player_merge_routes import merge_players
from app.services import sportsengine


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_merge_saves_duplicate_name_as_sync_alias():
    db = _session()
    keep_player = Player(
        full_name="Avery Johnson",
        parent_email="primary@example.com",
        date_of_birth=date(2018, 4, 9),
        birth_year=2018,
    )
    duplicate_player = Player(
        full_name="Avery J Johnson",
        parent_email="other@example.com",
        date_of_birth=date(2018, 4, 9),
        birth_year=2018,
    )
    db.add_all([keep_player, duplicate_player])
    db.commit()

    result = merge_players(
        {
            "keep_player_id": keep_player.id,
            "merge_player_ids": [duplicate_player.id],
        },
        db=db,
    )

    alias_player = find_player_by_alias(db, "Avery J. Johnson")

    assert result["success"] is True
    assert alias_player.id == keep_player.id
    assert db.query(Player).filter(Player.full_name == "Avery J Johnson").first() is None
    assert db.query(PlayerAlias).filter(
        PlayerAlias.normalized_alias == normalize_player_alias("Avery J Johnson")
    ).one().player_id == keep_player.id


def test_sportsengine_sync_matches_saved_player_alias():
    db = _session()
    keep_player = Player(
        full_name="Avery Johnson",
        parent_email="primary@example.com",
        date_of_birth=date(2018, 4, 9),
        birth_year=2018,
    )
    duplicate_player = Player(
        full_name="Avery J Johnson",
        parent_email="other@example.com",
        date_of_birth=date(2018, 4, 9),
        birth_year=2018,
    )
    db.add_all([keep_player, duplicate_player])
    db.commit()

    merge_players(
        {
            "keep_player_id": keep_player.id,
            "merge_player_ids": [duplicate_player.id],
        },
        db=db,
    )
    install_player_alias_sync_patch()

    matched_player = sportsengine._find_existing_player(db, "Avery J. Johnson")

    assert matched_player.id == keep_player.id

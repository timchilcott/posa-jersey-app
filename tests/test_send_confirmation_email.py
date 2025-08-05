import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure DATABASE_URL is set before importing application modules
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app.database import Base
from app.email import send_confirmation_email
from app.models import Player, Registration

import pytest


@pytest.fixture
def db_session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_email_body_lists_all_players(db_session, capsys):
    player1 = Player(full_name='Alice', parent_email='parent@example.com', jersey_number=5)
    player2 = Player(full_name='Bob', parent_email='parent@example.com', jersey_number=7)
    db_session.add_all([player1, player2])
    db_session.flush()

    reg1 = Registration(player_id=player1.id, program='Prog', division='U8', sport='soccer', season='2024')
    reg2 = Registration(player_id=player2.id, program='Prog', division='U8', sport='soccer', season='2024')
    db_session.add_all([reg1, reg2])
    db_session.commit()

    players = [
        {"name": player1.full_name, "jersey_number": player1.jersey_number},
        {"name": player2.full_name, "jersey_number": player2.jersey_number},
    ]

    send_confirmation_email(
        'parent@example.com',
        players,
        'http://order.example.com',
        registrations=[reg1, reg2],
        db=db_session,
        promo_code='CODE123',
    )

    captured = capsys.readouterr().out
    # Both players appear in the single logged email
    assert 'Alice' in captured
    assert 'Bob' in captured
    # Promo code appears for each player
    assert captured.count('Promo Code: CODE123') == 2
    # Registrations were marked as sent
    assert reg1.confirmation_sent and reg2.confirmation_sent

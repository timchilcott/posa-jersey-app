import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure database URL is set before importing application modules
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app.database import Base
from app.models import Player, Registration
from app.services.assign import assign_jersey_number

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

def test_assign_returns_lowest_unused(db_session):
    for num in [1, 2, 4]:
        player = Player(full_name=f'Player {num}', jersey_number=num, parent_email='p@example.com')
        db_session.add(player)
        db_session.flush()
        reg = Registration(
            player_id=player.id,
            program='prog',
            division='U8',
            sport='sport',
            season='2024'
        )
        db_session.add(reg)
    db_session.commit()
    assert assign_jersey_number(db_session, 'U8') == 3

def test_assign_fallback_when_all_taken(db_session):
    for num in range(1, 100):
        player = Player(full_name=f'Player {num}', jersey_number=num, parent_email=f'p{num}@ex.com')
        db_session.add(player)
        db_session.flush()
        reg = Registration(
            player_id=player.id,
            program='prog',
            division='U8',
            sport='sport',
            season='2024'
        )
        db_session.add(reg)
    db_session.commit()
    assert assign_jersey_number(db_session, 'U8') == 99

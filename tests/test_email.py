import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app.database import Base
from app.models import Player, Registration
from app.email import process_inbound_email

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


def test_promo_code_assignment(db_session):
    email = """
Name: Player One
Program: Winter Soccer
Division: U10
Parent Email: p1@example.com

Name: Player Two
Program: Winter Soccer
Division: U10
Parent Email: p2@example.com
"""
    process_inbound_email(email, db_session)
    regs = db_session.query(Registration).all()
    assert len(regs) == 2
    assert all(r.promo_code == 'Pines2Players' for r in regs)


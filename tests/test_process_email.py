import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure DATABASE_URL is set before importing application modules
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app.database import Base
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


def test_logs_missing_single_field(db_session, caplog):
    body = """
Name: John Doe
Program: Spring Soccer
Parent Email: p@example.com
"""
    with caplog.at_level(logging.WARNING):
        process_inbound_email(body, db_session)
    assert "Unknown division" in caplog.text


def test_logs_missing_multiple_fields(db_session, caplog):
    body = """
Program: Spring Soccer
Division: U12
"""
    with caplog.at_level(logging.WARNING):
        process_inbound_email(body, db_session)
    # Order of fields may vary
    assert "missing:" in caplog.text
    assert "Name" in caplog.text
    assert "Parent Email" in caplog.text

import os
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


def test_logs_missing_single_field(db_session, capsys):
    body = """Name: John Doe\nProgram: Spring Soccer\nParent Email: p@example.com"""
    process_inbound_email(body, db_session)
    captured = capsys.readouterr().out
    assert "missing: Division" in captured


def test_logs_missing_multiple_fields(db_session, capsys):
    body = """Program: Spring Soccer\nDivision: U12"""
    process_inbound_email(body, db_session)
    captured = capsys.readouterr().out
    # Order of fields may vary
    assert "missing:" in captured
    assert "Name" in captured
    assert "Parent Email" in captured

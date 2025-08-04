import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from starlette.requests import Request

# Ensure database URL is set before importing application modules
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app.database import Base
from app.models import Player, Registration
from app.services.assign import assign_jersey_number
from app.email import process_inbound_email
from app.main import admin_dashboard

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


def test_manual_high_school_registration(db_session):
    jersey = assign_jersey_number(db_session, 'High School')
    player = Player(full_name='HS Player', parent_email='parent@example.com', jersey_number=jersey)
    db_session.add(player)
    db_session.flush()
    reg = Registration(
        player_id=player.id,
        program='Fall Soccer',
        division='High School',
        sport='soccer',
        season='fall',
    )
    db_session.add(reg)
    db_session.commit()

    stored = db_session.query(Registration).filter_by(player_id=player.id).first()
    assert stored.division == 'High School'
    assert player.jersey_number == 1


def test_email_high_school_normalization(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Test HS'
    html = """
    <html><body>
    Name: John HS<br>
    Program: Fall Soccer<br>
    Division: High School<br>
    Parent Email: parent@example.com<br>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    reg = db_session.query(Registration).first()
    assert reg.division == 'High School'
    player = db_session.query(Player).first()
    assert player.jersey_number == 1


def test_admin_shows_high_school(db_session):
    jersey = assign_jersey_number(db_session, 'High School')
    player = Player(full_name='Admin HS', parent_email='admin@example.com', jersey_number=jersey)
    db_session.add(player)
    db_session.flush()
    reg = Registration(
        player_id=player.id,
        program='Fall Soccer',
        division='High School',
        sport='soccer',
        season='fall',
    )
    db_session.add(reg)
    db_session.commit()

    req = Request({'type': 'http', 'session': {'user_id': 1}})
    response = admin_dashboard(req, db_session)
    divisions = response.context['division_list']
    assert 'High School' in divisions
    assert '' not in divisions


def test_pend_oreille_alias(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Pend Oreille Test'
    html = """
    <html><body>
    Name: Alias HS<br>
    Program: Fall Soccer<br>
    Division: Pend Oreille Pines High School Club Team<br>
    Parent Email: parent@example.com<br>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    reg = db_session.query(Registration).first()
    assert reg.division == 'High School'
    divisions = {d for (d,) in db_session.query(Registration.division).distinct()}
    assert divisions == {'High School'}

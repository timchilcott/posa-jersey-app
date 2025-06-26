import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Ensure database URL is set before importing application modules
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

def test_html_email_parsing(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Test'
    html = """
    <html><body>
    Name: John Doe<br>
    Program: Fall Soccer<br>
    Division: U10<br>
    Parent Email: parent@example.com<br>
    Order Number: 12345<br>
    Order Date: January 1, 2024
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    player = db_session.query(Player).filter_by(full_name='John Doe').first()
    assert player is not None
    reg = db_session.query(Registration).filter_by(player_id=player.id).first()
    assert reg is not None
    assert reg.program == 'Fall Soccer'
    assert reg.division == 'U10'


def test_bluesombrero_fixture_parsing(db_session):
    fixture = os.path.join('tests', 'fixtures', 'bluesombrero_order.html')
    with open(fixture, 'r') as f:
        html = f.read()

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    player = db_session.query(Player).filter_by(full_name='Sally Smith').first()
    assert player is not None
    assert player.parent_email == 'sallyparent@example.com'

    reg = db_session.query(Registration).filter_by(player_id=player.id).first()
    assert reg is not None
    assert reg.program == 'Winter Basketball'
    assert reg.division == 'U12'
    assert reg.order_number == '987654321'
    assert reg.order_date == datetime(2024, 2, 10)

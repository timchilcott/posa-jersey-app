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
from datetime import datetime

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
def test_order_details_table_parsing(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr><td>Order Number</td><td>ABC123</td></tr>
        <tr><td>Order Date</td><td>January 2, 2024</td></tr>
        <tr><td><span>John Doe</span></td><td><span>Fall Soccer - U10</span></td></tr>
        <tr><td><span>Jane Doe</span></td><td><span>Fall Soccer - U8</span></td></tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).order_by(Player.full_name).all()
    assert [p.full_name for p in players] == ['Jane Doe', 'John Doe']
    for player in players:
        assert player.parent_email == 'parent@example.com'

    regs = db_session.query(Registration).order_by(Registration.division).all()
    assert len(regs) == 2
    assert all(r.order_number == 'ABC123' for r in regs)
    assert all(r.order_date.date() == datetime(2024, 1, 2).date() for r in regs)
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

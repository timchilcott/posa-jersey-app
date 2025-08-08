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
from app.email import process_inbound_email, PROMO_CODES

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


def test_order_date_row_skipped(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr><td><span>Order Date</span></td><td><span>January 2, 2024</span></td></tr>
        <tr><td><span>John Doe</span></td><td><span>Fall Soccer - U10</span></td></tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'

    regs = db_session.query(Registration).all()
    assert len(regs) == 1


def test_timestamp_row_skipped(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr><td><span>Aug 05, 2025 12:29 PM</span><span>Fall Soccer - U10</span></td></tr>
        <tr><td><span>John Doe</span></td><td><span>Fall Soccer - U10</span></td></tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'

    regs = db_session.query(Registration).all()
    assert len(regs) == 1
    promo_code = PROMO_CODES.get(len(regs))
    assert promo_code == PROMO_CODES.get(1)


def test_timestamp_span_removed(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr>
            <td><span>Aug 05, 2025 12:29 PM</span></td>
            <td><span>John Doe</span></td>
            <td><span>Fall Soccer - U10</span></td>
        </tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'

    regs = db_session.query(Registration).all()
    assert len(regs) == 1
    assert regs[0].program == 'Fall Soccer'
    assert regs[0].division == 'U10'


def test_weekday_timestamp_span_removed(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr>
            <td><span>Mon, Aug 05, 2025 12:29 PM</span></td>
            <td><span>John Doe</span></td>
            <td><span>Fall Soccer - U10</span></td>
        </tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'

    regs = db_session.query(Registration).all()
    assert len(regs) == 1
    assert regs[0].program == 'Fall Soccer'
    assert regs[0].division == 'U10'


def test_order_details_row_three_spans(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr><td><span>Aug 05, 2025 12:29 PM</span><span>John Doe</span><span>Fall Soccer - U10</span></td></tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'
    assert (
        db_session.query(Player)
        .filter_by(full_name='Aug 05, 2025 12:29 PM')
        .first()
        is None
    )

    regs = db_session.query(Registration).all()
    assert len(regs) == 1
    assert regs[0].program == 'Fall Soccer'
    assert regs[0].division == 'U10'


def test_jersey_number_span_removed(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr>
            <td><span>Aug 05, 2025 12:29 PM</span><span>Jersey Number: 7</span><span>John Doe</span></td>
            <td><span>Fall Soccer - U10</span></td>
        </tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'
    assert (
        db_session.query(Player).filter_by(full_name='Jersey Number: 7').first() is None
    )

    regs = db_session.query(Registration).all()
    assert len(regs) == 1
    assert regs[0].program == 'Fall Soccer'
    assert regs[0].division == 'U10'


def test_jersey_number_split_span_removed(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr>
            <td><span>Aug 05, 2025 12:29 PM</span><span>Jersey Number:</span><span>7</span><span>John Doe</span></td>
            <td><span>Fall Soccer - U10</span></td>
        </tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).all()
    assert len(players) == 1
    assert players[0].full_name == 'John Doe'
    assert db_session.query(Player).filter_by(full_name='7').first() is None

    regs = db_session.query(Registration).all()
    assert len(regs) == 1
    assert regs[0].program == 'Fall Soccer'
    assert regs[0].division == 'U10'


def test_price_row_skipped_and_promo_code(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr><td>Order Number</td><td>ABC123</td></tr>
        <tr><td>Order Date</td><td>January 2, 2024</td></tr>
        <tr><td><span>$35.00</span></td><td><span>Fall Soccer - U10</span></td></tr>
        <tr><td><span>John Doe</span></td><td><span>Fall Soccer - U10</span></td></tr>
        <tr><td><span>Jane Smith</span></td><td><span>Fall Soccer - U8</span></td></tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).order_by(Player.full_name).all()
    assert [p.full_name for p in players] == ['Jane Smith', 'John Doe']
    assert db_session.query(Player).filter_by(full_name='$35.00').first() is None

    regs = db_session.query(Registration).order_by(Registration.division).all()
    assert len(regs) == 2
    promo_code = PROMO_CODES.get(len(regs))
    assert promo_code == PROMO_CODES.get(2)


def test_price_span_with_extra_content_skipped(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Order'
    msg['To'] = 'parent@example.com'
    html = """
    <html><body>
    <table>
        <tr><td>Order Details</td></tr>
        <tr><td>Order Number</td><td>ABC123</td></tr>
        <tr><td>Order Date</td><td>January 2, 2024</td></tr>
        <tr><td><span>$50.00</span><span>Maverick West</span></td><td><span>Fall Soccer - U10</span></td></tr>
        <tr><td><span>John Doe</span></td><td><span>Fall Soccer - U10</span></td></tr>
        <tr><td><span>Jane Smith</span></td><td><span>Fall Soccer - U8</span></td></tr>
    </table>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    players = db_session.query(Player).order_by(Player.full_name).all()
    assert [p.full_name for p in players] == ['Jane Smith', 'John Doe']
    assert db_session.query(Player).filter_by(full_name='Maverick West').first() is None

    regs = db_session.query(Registration).order_by(Registration.division).all()
    assert len(regs) == 2
    promo_code = PROMO_CODES.get(len(regs))
    assert promo_code == PROMO_CODES.get(2)


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


def test_update_division_for_existing_player(db_session):
    first = MIMEMultipart('alternative')
    first['Subject'] = 'First'
    html1 = """
    <html><body>
    Name: John Doe<br>
    Program: Spring Soccer<br>
    Division: U10<br>
    Parent Email: parent@example.com<br>
    </body></html>
    """
    first.attach(MIMEText(html1, 'html'))

    process_inbound_email(first.as_string(), db_session)

    player = db_session.query(Player).filter_by(full_name='John Doe').first()
    reg = db_session.query(Registration).filter_by(player_id=player.id).first()
    assert reg.division == 'U10'

    second = MIMEMultipart('alternative')
    second['Subject'] = 'Second'
    html2 = """
    <html><body>
    Name: John Doe<br>
    Program: Spring Soccer<br>
    Division: U12<br>
    Parent Email: parent@example.com<br>
    </body></html>
    """
    second.attach(MIMEText(html2, 'html'))

    process_inbound_email(second.as_string(), db_session)

    reg_updated = db_session.query(Registration).filter_by(player_id=player.id, sport='soccer', season='spring').first()
    assert reg_updated.division == 'U12'
    assert db_session.query(Registration).count() == 1


def test_division_normalization(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Normalize'
    html = """
    <html><body>
    Name: Alice Smith<br>
    Program: Fall Soccer<br>
    Division: Under 10<br>
    Parent Email: alice@example.com<br>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    reg = db_session.query(Registration).first()
    assert reg.division == 'U10'


def test_unknown_division_defaults(db_session, capsys):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Unknown'
    html = """
    <html><body>
    Name: Bob Brown<br>
    Program: Fall Soccer<br>
    Division: Galactic<br>
    Parent Email: bob@example.com<br>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)
    captured = capsys.readouterr().out
    assert "Unknown division" in captured
    reg = db_session.query(Registration).first()
    assert reg.division == 'Unknown'


def test_missing_division_defaults_to_pines_team(db_session):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Missing Division'
    html = """
    <html><body>
    Name: Sam Student<br>
    Program: High School Soccer<br>
    Parent Email: sam@example.com<br>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html'))

    process_inbound_email(msg.as_string(), db_session)

    reg = db_session.query(Registration).first()
    assert reg.division == 'Pend Oreille Pines (High School Club Team)'

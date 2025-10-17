import os
import re
import email
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from .models import Player, Registration
from .services.assign import assign_jersey_number

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
PROMO_CODES = {
    1: "Pines1Player",
    2: "Pines2Players",
    3: "Pines3Players",
    4: "Pines4Players",
    5: "Pines5Players",
    6: "Pines6Players",
    7: "Pines7Players",
}

UNIFORM_ORDER_URL = (
    "https://treblemade.com/products/pines-soccer-reversible-jersey?_pos=1&_sid=0fa41b461&_ss=r"
)
DEFAULT_CC_EMAIL = "tim@posasports.org"

DIVISION_ORDER = {
    "U3": -1,
    "U4": 0,
    "U5": 1,
    "U6": 2,
    "U8": 3,
    "U10": 4,
    "U12": 5,
    "U14": 6,
    "Pend Oreille Pines (High School Club Team)": 7,
}

DIVISION_ALIASES = {
    "U3": "U3",
    "UNDER3": "U3",
    "U4": "U4",
    "UNDER4": "U4",
    "U5": "U5",
    "UNDER5": "U5",
    "U6": "U6",
    "UNDER6": "U6",
    "U8": "U8",
    "UNDER8": "U8",
    "U10": "U10",
    "UNDER10": "U10",
    "U12": "U12",
    "UNDER12": "U12",
    "U14": "U14",
    "UNDER14": "U14",
    "HIGHSCHOOL": "Pend Oreille Pines (High School Club Team)",
    "HS": "Pend Oreille Pines (High School Club Team)",
    "PENDOREILLEPINESHIGHSCHOOLCLUBTEAM": "Pend Oreille Pines (High School Club Team)",
}

# ---------------------------------------------------------------------
# Division normalization
# ---------------------------------------------------------------------
def normalize_division(raw: str, birth_year: int | None = None) -> str:
    """Map various division strings to canonical form, applying POSA's 2022→U3 rule."""
    key = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    if key in DIVISION_ALIASES:
        return DIVISION_ALIASES[key]
    if birth_year == 2022:
        return "U3"
    division = DIVISION_ALIASES.get(key, key)
    return division if division in DIVISION_ORDER else "Unknown"

# ---------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------
def _plain_text_from_html(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text("\n")

# ---------------------------------------------------------------------
# Outbound confirmation emails
# ---------------------------------------------------------------------
def send_confirmation_email(to_email, players, promo_code=None, registrations=None, db=None):
    """Send registration confirmation for youth divisions."""
    from .models import EmailTemplate

    template = None
    if db:
        template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.name == "standard_confirmation")
            .first()
        )

    players_html = "\n".join(
        f"<p>Player: {p['name']} (#{p['jersey_number']}) - {p['sport']}</p>"
        for p in players
    )
    unique_sports = sorted(set(p["sport"] for p in players))
    sport_text = ", ".join(unique_sports) if unique_sports else "Unknown"

    if template:
        subject = template.subject
        html = template.body_html
        html = (
            html.replace("{player_list}", players_html)
            .replace("{promo_code}", promo_code or "")
            .replace("{uniform_url}", UNIFORM_ORDER_URL)
            .replace("{sport}", sport_text)
        )
    else:
        promo_html = f"<p>Promo Code: {promo_code}</p>" if promo_code else ""
        subject = "Jersey Numbers and Uniform Info for Your Player(s)"
        html = (
            "<p>Thanks for signing up for soccer with the Pend Oreille Pines!</p>"
            f"{players_html}"
            f"{promo_html}"
            f"<p>Order jerseys here: <a href='{UNIFORM_ORDER_URL}'>{UNIFORM_ORDER_URL}</a></p>"
            "<p>Only the reversible Pines jersey is required for games. Plain black shorts and socks are fine as long as they have no other team logos or colors.</p>"
            "<p>If your family can purchase jerseys without using promo codes, it helps our nonprofit stretch funds for others. Either way, we're thrilled to have your kids on the field.</p>"
            "<p>—<br>Tim Chilcott<br>President - POSA<br>🌲 Pines stand tall.<br>❤️ The heart of sports starts with us.</p>"
        )

    message = Mail(
        from_email="noreply@posasports.org",
        to_emails=to_email,
        subject=subject,
        html_content=html,
        plain_text_content=_plain_text_from_html(html),
    )
    if to_email != DEFAULT_CC_EMAIL:
        message.add_cc(DEFAULT_CC_EMAIL)

    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        logger.debug("SendGrid status=%s", response.status_code)
        if registrations and db and 200 <= response.status_code < 300:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    except Exception as e:
        logger.error("Error sending confirmation email: %s", e)

def send_pines_confirmation_email(to_email, players, registrations=None, db=None):
    """Send registration confirmation for the HS Club (Pend Oreille Pines)."""
    from .models import EmailTemplate

    template = None
    if db:
        template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.name == "pines_confirmation")
            .first()
        )

    players_html = "\n".join(
        f"<p>{p['name']}<br>Jersey Number: {p['jersey_number']}<br>Sport: {p['sport']}</p>"
        for p in players
    )
    unique_sports = sorted(set(p["sport"] for p in players))
    sport_text = ", ".join(unique_sports) if unique_sports else "Unknown"

    if template:
        subject = template.subject
        html = template.body_html
        html = (
            html.replace("{player_list}", players_html)
            .replace("{uniform_url}", UNIFORM_ORDER_URL)
            .replace("{sport}", sport_text)
        )
    else:
        subject = "Jersey Numbers and Uniform Info for Your Player(s)"
        html = (
            "<p>Thanks for registering with the Pend Oreille Pines High School Club Team.</p>"
            f"{players_html}"
            f"<p>Order your kit here:<br><a href='{UNIFORM_ORDER_URL}'>{UNIFORM_ORDER_URL}</a></p>"
            "<p><strong>Uniform Requirements:</strong> Reversible Pines jersey, black shorts, black socks.</p>"
            "<p>Club players purchase their own kits; promo codes are not used for this division.</p>"
            "<p>—<br>Tim Chilcott<br>President - POSA<br>🌲 Pines stand tall.<br>❤️ The heart of sports starts with us.</p>"
        )

    message = Mail(
        from_email="noreply@posasports.org",
        to_emails=to_email,
        subject=subject,
        html_content=html,
        plain_text_content=_plain_text_from_html(html),
    )
    if to_email != DEFAULT_CC_EMAIL:
        message.add_cc(DEFAULT_CC_EMAIL)

    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        logger.debug("SendGrid status=%s", response.status_code)
        if registrations and db and 200 <= response.status_code < 300:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    except Exception as e:
        logger.error("Error sending Pines confirmation email: %s", e)

# ---------------------------------------------------------------------
# Inbound email capture / parsing
# ---------------------------------------------------------------------
def save_inbound_email(email_body: str, filename: str | None = None) -> None:
    root_dir = os.path.dirname(os.path.dirname(__file__))
    if not filename:
        filename = f"captured_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(os.path.join(root_dir, filename), "w") as f:
            f.write(email_body)
        logger.info("Saved inbound email to %s", filename)
    except Exception as e:
        logger.error("Failed to save inbound email: %s", e)

def process_inbound_email(email_body: str, db):
    """Parse inbound email and create player/registration records in Waiting Room."""
    logger.info("Processing inbound email")
    
    try:
        # Parse the email
        msg = email.message_from_string(email_body)
        
        # Get parent email from To: field
        parent_email = None
        to_header = msg.get('To', '')
        if to_header:
            # Extract email from "Name <email@example.com>" format
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
            if email_match:
                parent_email = email_match.group(0)
        
        # Get HTML content
        html_content = None
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    charset = part.get_content_charset() or "utf-8"
                    html_content = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
        else:
            if msg.get_content_type() == "text/html":
                charset = msg.get_content_charset() or "utf-8"
                html_content = msg.get_payload(decode=True).decode(charset, errors="replace")
        
        if not html_content:
            html_content = email_body
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract order number
        order_number = None
        order_no_match = re.search(r'Order No:\s*(\d+)', soup.get_text())
        if order_no_match:
            order_number = order_no_match.group(1)
        
        # Extract order date
        order_date = None
        order_date_match = re.search(r'Order Date.*?(\w{3} \d{1,2}, \d{4})', soup.get_text())
        if order_date_match:
            try:
                order_date = datetime.strptime(order_date_match.group(1), '%b %d, %Y')
            except:
                pass
        
        text_content = soup.get_text()
        
        # UPDATED PATTERN: Handles hyphens, apostrophes, and multiple names
        # Examples: "John Smith", "Mary-Jane O'Connor", "José García-López"
        # Pattern breakdown:
        # \d+ = digit(s) before name (order quantity)
        # (?:[A-Z][a-z]+(?:[-\'\s])?)+ = one or more capitalized words, optionally separated by hyphen/apostrophe/space
        # \s*(\d{4}) = year (2025, etc.)
        # \s+Pines\s+(\w+) = "Pines" followed by sport name
        # \s*-?\s*(.+?) = optional dash and rest of division info
        pattern1 = re.search(
            r'\d+((?:[A-Z][a-z]+(?:[-\'\s])?)+)\s*(\d{4})\s+Pines\s+(\w+)\s*-?\s*(.+?)(?=\$|Division|$)', 
            text_content
        )
        
        if pattern1:
            player_name = pattern1.group(1).strip()
            year = pattern1.group(2)
            sport = pattern1.group(3).strip().lower()
            division_info = pattern1.group(4).strip() if pattern1.group(4) else ""
            
            logger.info(f"Found player: {player_name}, sport: {sport}, captured division info: {division_info}")
            
            # Check if player already exists
            existing_player = db.query(Player).filter(Player.full_name == player_name).first()
            
            if existing_player:
                # Check if registration exists for this sport/season
                existing_reg = db.query(Registration).filter(
                    Registration.player_id == existing_player.id,
                    Registration.sport == sport,
                    Registration.season == year
                ).first()
                
                if existing_reg:
                    logger.info(f"Registration already exists for {player_name} in {sport} {year}")
                else:
                    # Add new registration to Waiting Room
                    new_reg = Registration(
                        player_id=existing_player.id,
                        program=f"{year} Pines {sport.title()}",
                        division="Waiting Room",
                        sport=sport,
                        season=year,
                        order_number=order_number,
                        order_date=order_date,
                        confirmation_sent=False
                    )
                    db.add(new_reg)
                    logger.info(f"Added new registration to Waiting Room for {player_name}")
            else:
                # Create new player without jersey number or birth year - admin will assign
                new_player = Player(
                    full_name=player_name,
                    parent_email=parent_email or "unknown@example.com",
                    jersey_number=None,
                    birth_year=None
                )
                db.add(new_player)
                db.flush()
                
                # Create registration in Waiting Room
                new_reg = Registration(
                    player_id=new_player.id,
                    program=f"{year} Pines {sport.title()}",
                    division="Waiting Room",
                    sport=sport,
                    season=year,
                    order_number=order_number,
                    order_date=order_date,
                    confirmation_sent=False
                )
                db.add(new_reg)
                logger.info(f"Created new player {player_name} in Waiting Room (no jersey/birth year yet)")
            
            db.commit()
            logger.info("Email processed successfully - player in Waiting Room")
        else:
            logger.warning("Could not parse player information from email")
            logger.debug(f"Email text content preview: {text_content[:500]}")
            
    except Exception as e:
        logger.error(f"Error processing inbound email: {e}", exc_info=True)
        db.rollback()

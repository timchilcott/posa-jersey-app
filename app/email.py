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
        
        # Get parent email - try multiple methods
        parent_email = None
        
        # Method 1: Look for forwarded "To:" field in the body
        forwarded_to_match = re.search(r'>\s*To:\s*([\w\.-]+@[\w\.-]+\.\w+)', email_body)
        if forwarded_to_match:
            parent_email = forwarded_to_match.group(1)
            logger.info(f"Found parent email from forwarded message: {parent_email}")
        
        # Method 2: Check To: header
        if not parent_email:
            to_header = msg.get('To', '')
            if to_header:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
                if email_match:
                    parent_email = email_match.group(0)
                    logger.info(f"Found parent email from To header: {parent_email}")
        
        # Method 3: Look in the body for an email address
        if not parent_email:
            body_email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email_body)
            if body_email_match:
                potential_email = body_email_match.group(0)
                # Exclude common system emails
                if not any(x in potential_email.lower() for x in ['noreply', 'donotreply', 'system', 'admin', 'posasports.org']):
                    parent_email = potential_email
                    logger.info(f"Found parent email from body: {parent_email}")
        
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
        
        # Parse HTML with BeautifulSoup - use separator to preserve spacing
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract order number
        order_number = None
        order_no_match = re.search(r'Order\s*No:?\s*(\d+)', soup.get_text(), re.IGNORECASE)
        if order_no_match:
            order_number = order_no_match.group(1)
            logger.info(f"Found order number: {order_number}")
        
        # Extract order date
        order_date = None
        # Try multiple date formats
        date_patterns = [
            (r'Order Date.*?(\w{3}\s+\d{1,2},\s+\d{4})', '%b %d, %Y'),
            (r'(\w{3}\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2}\s+[AP]M)', '%b %d, %Y %I:%M %p'),
        ]
        for pattern, date_format in date_patterns:
            order_date_match = re.search(pattern, soup.get_text())
            if order_date_match:
                try:
                    order_date = datetime.strptime(order_date_match.group(1), date_format)
                    logger.info(f"Found order date: {order_date}")
                    break
                except:
                    pass
        
        # Get text with some spacing preservation
        full_text = soup.get_text(separator=' ', strip=True)
        
        # CRITICAL FIX: Extract only the Order Details section
        # This prevents matching promotional text like "Thank you for signing up"
        order_details_section = None
        order_details_match = re.search(
            r'Order Details:.*?(?:Total:|Program Info:|$)',
            full_text,
            re.IGNORECASE | re.DOTALL
        )
        if order_details_match:
            order_details_section = order_details_match.group(0)
            logger.info(f"Extracted Order Details section: {order_details_section[:200]}")
        else:
            # Fallback: try to find any section with player registration info
            order_details_match = re.search(
                r'(?:Amount|Balance).*?(?:Total:|Program Info:|$)',
                full_text,
                re.IGNORECASE | re.DOTALL
            )
            if order_details_match:
                order_details_section = order_details_match.group(0)
                logger.info(f"Extracted fallback section: {order_details_section[:200]}")
        
        # If we found an order details section, use it; otherwise use full text
        text_to_parse = order_details_section if order_details_section else full_text
        
        # Try multiple patterns to extract player information
        player_found = False
        player_name = None
        year = None
        sport = None
        
        # Invalid name patterns to filter out
        invalid_names = [
            'thank you', 'signing up', 'order details', 'program info',
            'order date', 'order total', 'open balance', 'view order',
            'amount balance', 'division price', 'non-volunteer'
        ]
        
        def is_valid_name(name):
            """Check if extracted name is actually a person's name."""
            name_lower = name.lower()
            # Must be 2-4 words
            words = name.split()
            if len(words) < 2 or len(words) > 4:
                return False
            # Each word should be reasonable length
            if any(len(w) < 2 or len(w) > 20 for w in words):
                return False
            # Should not contain invalid phrases
            if any(invalid in name_lower for invalid in invalid_names):
                return False
            # Should start with capital letter
            if not name[0].isupper():
                return False
            return True
        
        # Patterns specifically for Order Details section
        patterns = [
            # Pattern 1: Digit followed by name, year, Pines, sport
            r'(?:\d+\s*)([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(\d{4})\s+pines\s+(\w+)',
            # Pattern 2: Name year pines sport (more flexible spacing)
            r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(\d{4})\s*pines\s*(\w+)',
            # Pattern 3: Look for name followed by year and explicit sports
            r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(\d{4}).*?(volleyball|soccer|basketball|baseball|softball|flag)',
        ]
        
        for i, pattern in enumerate(patterns, 1):
            matches = re.finditer(pattern, text_to_parse, re.IGNORECASE)
            for match in matches:
                potential_name = match.group(1).strip()
                if is_valid_name(potential_name):
                    player_name = potential_name
                    year = match.group(2)
                    sport = match.group(3).strip().lower()
                    logger.info(f"Pattern {i} matched - Player: {player_name}, sport: {sport}, year: {year}")
                    break
            if player_name:
                break
        
        if player_name and year and sport:
            logger.info(f"Successfully parsed - Player: {player_name}, sport: {sport}, year: {year}")
            
            # Extract division/grade info if present (like "3rd/4th Grade")
            division_info = None
            grade_patterns = [
                r'(\d+(?:st|nd|rd|th)/\d+(?:st|nd|rd|th)\s+grade)',
                r'(grade\s+\d+)',
                r'(k-\d+)',
                r'(kindergarten)',
            ]
            for grade_pattern in grade_patterns:
                division_match = re.search(grade_pattern, text_to_parse, re.IGNORECASE)
                if division_match:
                    division_info = division_match.group(1)
                    logger.info(f"Found grade/division info: {division_info}")
                    break
            
            # Always start in Waiting Room - admin will assign proper division
            division = "Waiting Room"
            
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
                    # Update order info if it was missing
                    if not existing_reg.order_number and order_number:
                        existing_reg.order_number = order_number
                        existing_reg.order_date = order_date
                        db.commit()
                        logger.info(f"Updated order info for existing registration")
                else:
                    # Add new registration to Waiting Room
                    program_name = f"{year} Pines {sport.title()}"
                    if division_info:
                        program_name += f" - {division_info}"
                    
                    new_reg = Registration(
                        player_id=existing_player.id,
                        program=program_name,
                        division=division,
                        sport=sport,
                        season=year,
                        order_number=order_number,
                        order_date=order_date,
                        confirmation_sent=False
                    )
                    db.add(new_reg)
                    db.commit()
                    logger.info(f"Added new registration to Waiting Room for {player_name}")
                    player_found = True
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
                program_name = f"{year} Pines {sport.title()}"
                if division_info:
                    program_name += f" - {division_info}"
                
                new_reg = Registration(
                    player_id=new_player.id,
                    program=program_name,
                    division=division,
                    sport=sport,
                    season=year,
                    order_number=order_number,
                    order_date=order_date,
                    confirmation_sent=False
                )
                db.add(new_reg)
                db.commit()
                logger.info(f"Created new player {player_name} in Waiting Room")
                player_found = True
        
        if not player_found:
            logger.warning("Could not parse player information from email")
            logger.debug(f"Order Details section (first 500 chars):\n{text_to_parse[:500] if text_to_parse else 'N/A'}")
            logger.debug(f"Full email preview (first 1000 chars):\n{full_text[:1000]}")
            
    except Exception as e:
        logger.error(f"Error processing inbound email: {e}", exc_info=True)
        db.rollback()

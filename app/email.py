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

def parse_division_from_grade(grade: str) -> str:
    """
    Parse division from grade string.
    Examples: "3rd/4th Grade" -> "U10", "K/1st Grade" -> "U6"
    """
    grade = grade.lower()
    
    # Extract highest grade number
    numbers = re.findall(r'(\d+)(?:st|nd|rd|th)', grade)
    
    if not numbers:
        # Check for Kindergarten
        if 'k' in grade or 'kindergarten' in grade:
            return "U6"
        return "Waiting Room"
    
    # Convert grade to division
    highest_grade = max(int(n) for n in numbers)
    
    grade_to_division = {
        0: "U6",   # Kindergarten
        1: "U6",   # 1st grade
        2: "U8",   # 2nd grade
        3: "U10",  # 3rd grade
        4: "U10",  # 4th grade
        5: "U12",  # 5th grade
        6: "U12",  # 6th grade
        7: "U14",  # 7th grade
        8: "U14",  # 8th grade
        9: "Pend Oreille Pines (High School Club Team)",  # High school
        10: "Pend Oreille Pines (High School Club Team)",
        11: "Pend Oreille Pines (High School Club Team)",
        12: "Pend Oreille Pines (High School Club Team)",
    }
    
    return grade_to_division.get(highest_grade, "Waiting Room")

def process_inbound_email(email_body: str, db):
    """Parse inbound email and create player/registration records in Waiting Room."""
    logger.info("=" * 80)
    logger.info("PROCESSING INBOUND EMAIL - START")
    logger.info("=" * 80)
    
    try:
        # Parse the email
        msg = email.message_from_string(email_body)
        
        # Get parent email
        parent_email = None
        forwarded_to_match = re.search(r'>\s*To:\s*([\w\.-]+@[\w\.-]+\.\w+)', email_body)
        if forwarded_to_match:
            parent_email = forwarded_to_match.group(1)
            logger.info(f"✓ Parent email: {parent_email}")
        
        if not parent_email:
            to_header = msg.get('To', '')
            if to_header:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
                if email_match:
                    parent_email = email_match.group(0)
                    logger.info(f"✓ Parent email from header: {parent_email}")
        
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
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract order info
        order_number = None
        order_no_match = re.search(r'Order\s*No:?\s*(\d+)', soup.get_text(), re.IGNORECASE)
        if order_no_match:
            order_number = order_no_match.group(1)
            logger.info(f"✓ Order number: {order_number}")
        
        order_date = None
        date_match = re.search(r'Order Date:[\s\w]+(\w{3}\s+\d{1,2},\s+\d{4})', soup.get_text())
        if date_match:
            try:
                order_date = datetime.strptime(date_match.group(1), '%b %d, %Y')
                logger.info(f"✓ Order date: {order_date}")
            except:
                pass
        
        # Get full text
        full_text = soup.get_text(separator=' ', strip=True)
        
        # LOG EVERYTHING TO CONSOLE
        logger.info("\n" + "=" * 80)
        logger.info("FULL EXTRACTED TEXT (first 2000 characters)")
        logger.info("=" * 80)
        logger.info(full_text[:2000])
        logger.info("...")
        logger.info("=" * 80)
        logger.info(f"Total length: {len(full_text)} characters")
        logger.info("=" * 80 + "\n")
        
        # Try to isolate Order Details section
        order_section = None
        
        # Method 1: Find "Order Details:" and extract next 500 chars
        match = re.search(r'Order Details:(.{50,1000}?)(?:Total:|Program Info:|Division Price:|$)', full_text, re.IGNORECASE | re.DOTALL)
        if match:
            order_section = match.group(1).strip()
            logger.info("✓ Found Order Details section:")
            logger.info("-" * 80)
            logger.info(order_section)
            logger.info("-" * 80 + "\n")
        else:
            logger.warning("⚠ Could not find Order Details section, using full text")
            order_section = full_text
        
        # NOW TRY PARSING - IMPROVED PATTERNS
        player_name = None
        year = None
        sport = None
        grade = None
        
        # Test each pattern individually and log results
        patterns = [
            # Pattern 1: With grade info (NEW)
            (r'\d+([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(\d{4})\s+Pines\s+(\w+)\s*-\s*([^$]+?)(?=\$|$)', "Pattern 1: digit+name+year+pines+sport+grade"),
            # Pattern 2: Without grade
            (r'\d+([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(\d{4})\s+Pines\s+(\w+)', "Pattern 2: digit+name+year+pines+sport"),
            # Pattern 3: Case insensitive
            (r'([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\s+(\d{4})\s+Pines\s+(volleyball|soccer|basketball|baseball|softball|flag)', "Pattern 3: name+year+pines+sport (case-insensitive)"),
            # Pattern 4: Lenient
            (r'([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\s*(\d{4}).*?(volleyball|soccer|basketball|baseball|softball)', "Pattern 4: lenient name year sport"),
        ]
        
        for pattern, description in patterns:
            logger.info(f"Testing: {description}")
            matches = list(re.finditer(pattern, order_section, re.IGNORECASE))
            logger.info(f"  Found {len(matches)} potential matches")
            
            for i, match in enumerate(matches, 1):
                name = match.group(1).strip()
                yr = match.group(2)
                sp = match.group(3).strip().lower()
                
                # Extract grade if available (Pattern 1)
                gr = None
                if len(match.groups()) > 3:
                    gr = match.group(4).strip()
                
                logger.info(f"  Match {i}: '{name}' | {yr} | {sp} | {gr or 'no grade'}")
                
                # Validate
                invalid = ['thank', 'signing', 'order', 'total', 'balance', 'amount', 'division', 'price', 'volunteer', 'fee']
                if any(kw in name.lower() for kw in invalid):
                    logger.info(f"    ✗ Rejected (contains invalid keyword)")
                    continue
                
                if len(name.split()) < 2:
                    logger.info(f"    ✗ Rejected (less than 2 words)")
                    continue
                
                # Validate year
                try:
                    year_int = int(yr)
                    current_year = datetime.now().year
                    if not (current_year - 20 <= year_int <= current_year + 5):
                        logger.info(f"    ✗ Rejected (invalid year: {yr})")
                        continue
                except:
                    logger.info(f"    ✗ Rejected (invalid year format)")
                    continue
                
                logger.info(f"    ✓ VALID! Using this match")
                player_name = name
                year = yr
                sport = sp
                grade = gr
                break
            
            if player_name:
                break
            else:
                logger.info(f"  No valid matches from this pattern\n")
        
        # RESULT
        if player_name and year and sport:
            logger.info("\n" + "=" * 80)
            logger.info("✓✓✓ SUCCESSFULLY PARSED ✓✓✓")
            logger.info(f"  Player: {player_name}")
            logger.info(f"  Year: {year}")
            logger.info(f"  Sport: {sport}")
            if grade:
                logger.info(f"  Grade: {grade}")
            logger.info("=" * 80 + "\n")
            
            # Determine division from grade or default to Waiting Room
            if grade:
                division = parse_division_from_grade(grade)
                logger.info(f"✓ Parsed division from grade: {division}")
            else:
                division = "Waiting Room"
            
            # Create/update player
            existing_player = db.query(Player).filter(Player.full_name == player_name).first()
            
            if existing_player:
                existing_reg = db.query(Registration).filter(
                    Registration.player_id == existing_player.id,
                    Registration.sport == sport,
                    Registration.season == year
                ).first()
                
                if existing_reg:
                    logger.info(f"Registration already exists for {player_name}")
                    if not existing_reg.order_number and order_number:
                        existing_reg.order_number = order_number
                        existing_reg.order_date = order_date
                        db.commit()
                        logger.info("✓ Updated order info")
                else:
                    program_name = f"{year} Pines {sport.title()}"
                    if grade:
                        program_name += f" - {grade}"
                    
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
                    logger.info(f"✓ Added registration for {player_name}")
            else:
                new_player = Player(
                    full_name=player_name,
                    parent_email=parent_email or "unknown@example.com",
                    jersey_number=None,
                    birth_year=None
                )
                db.add(new_player)
                db.flush()
                
                program_name = f"{year} Pines {sport.title()}"
                if grade:
                    program_name += f" - {grade}"
                
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
                logger.info(f"✓ Created new player {player_name}")
            
            logger.info("SUCCESS - Email processed")
        else:
            logger.error("\n" + "=" * 80)
            logger.error("✗✗✗ PARSING FAILED ✗✗✗")
            logger.error("Could not extract valid player information")
            logger.error("Review the extracted text and patterns above")
            logger.error("=" * 80)
            
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"✗✗✗ EXCEPTION ✗✗✗")
        logger.error(f"Error: {e}", exc_info=True)
        logger.error("=" * 80)
        db.rollback()

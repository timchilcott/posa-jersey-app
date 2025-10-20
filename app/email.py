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
    logger.info("=" * 60)
    logger.info("Processing inbound email - START")
    logger.info("=" * 60)
    
    try:
        # Parse the email
        msg = email.message_from_string(email_body)
        
        # Get parent email - try multiple methods
        parent_email = None
        
        # Method 1: Look for forwarded "To:" field in the body
        forwarded_to_match = re.search(r'>\s*To:\s*([\w\.-]+@[\w\.-]+\.\w+)', email_body)
        if forwarded_to_match:
            parent_email = forwarded_to_match.group(1)
            logger.info(f"✓ Found parent email from forwarded message: {parent_email}")
        
        # Method 2: Check To: header
        if not parent_email:
            to_header = msg.get('To', '')
            if to_header:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
                if email_match:
                    parent_email = email_match.group(0)
                    logger.info(f"✓ Found parent email from To header: {parent_email}")
        
        # Method 3: Look in the body for an email address
        if not parent_email:
            body_email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email_body)
            if body_email_match:
                potential_email = body_email_match.group(0)
                # Exclude common system emails
                if not any(x in potential_email.lower() for x in ['noreply', 'donotreply', 'system', 'admin', 'posasports.org']):
                    parent_email = potential_email
                    logger.info(f"✓ Found parent email from body: {parent_email}")
        
        if not parent_email:
            logger.warning("⚠ No parent email found - will use unknown@example.com")
        
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
            logger.info("Using plain text email body")
        else:
            logger.info("✓ Extracted HTML content")
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract order number
        order_number = None
        order_no_match = re.search(r'Order\s*No:?\s*(\d+)', soup.get_text(), re.IGNORECASE)
        if order_no_match:
            order_number = order_no_match.group(1)
            logger.info(f"✓ Found order number: {order_number}")
        else:
            logger.warning("⚠ No order number found")
        
        # Extract order date
        order_date = None
        date_patterns = [
            (r'Order Date.*?(\w{3}\s+\d{1,2},\s+\d{4})', '%b %d, %Y'),
            (r'(\w{3}\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2}\s+[AP]M)', '%b %d, %Y %I:%M %p'),
        ]
        for pattern, date_format in date_patterns:
            order_date_match = re.search(pattern, soup.get_text())
            if order_date_match:
                try:
                    order_date = datetime.strptime(order_date_match.group(1), date_format)
                    logger.info(f"✓ Found order date: {order_date}")
                    break
                except:
                    pass
        
        if not order_date:
            logger.warning("⚠ No order date found")
        
        # METHOD 1: Try to parse HTML table structure directly
        logger.info("\n--- METHOD 1: Parsing HTML table structure ---")
        player_from_table = None
        
        # Look for tables that might contain order details
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables in email")
        
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            logger.info(f"  Table {i+1}: {len(rows)} rows")
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    # Get text from all cells
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    combined = ' '.join(cell_texts)
                    
                    # Look for player pattern in this row
                    match = re.search(
                        r'(?:\d+)?\s*([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(\d{4})\s*[Pp]ines\s*(\w+)',
                        combined,
                        re.IGNORECASE
                    )
                    
                    if match:
                        name = match.group(1).strip()
                        year = match.group(2)
                        sport = match.group(3).strip().lower()
                        
                        # Validate it's not promotional text
                        if not any(x in name.lower() for x in ['thank', 'signing', 'order', 'total']):
                            logger.info(f"  ✓ Found in table row: {name} - {year} - {sport}")
                            player_from_table = (name, year, sport, combined)
                            break
            
            if player_from_table:
                break
        
        # METHOD 2: Extract text and parse with patterns
        logger.info("\n--- METHOD 2: Text extraction and pattern matching ---")
        
        # Get full text with spacing
        full_text = soup.get_text(separator=' ', strip=True)
        logger.info(f"Full text length: {len(full_text)} characters")
        
        # Try to find Order Details section
        order_section = None
        section_patterns = [
            r'Order Details:.*?(?:Total:|Program Info:|Division Price|$)',
            r'Order Details.*?(?:\$\d+\.\d+.*?\$\d+\.\d+)',
            r'(?:Amount.*?Balance).*?(?:Total:|$)',
        ]
        
        for i, pattern in enumerate(section_patterns, 1):
            match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
            if match:
                order_section = match.group(0)
                logger.info(f"✓ Found order section using pattern {i}")
                logger.info(f"  Section preview: {order_section[:200]}...")
                break
        
        if not order_section:
            logger.warning("⚠ Could not isolate Order Details section, using full text")
            order_section = full_text
        
        # Save debug info
        debug_file = f"debug_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            root_dir = os.path.dirname(os.path.dirname(__file__))
            with open(os.path.join(root_dir, debug_file), 'w') as f:
                f.write("="*60 + "\n")
                f.write("FULL TEXT\n")
                f.write("="*60 + "\n")
                f.write(full_text)
                f.write("\n\n")
                f.write("="*60 + "\n")
                f.write("ORDER SECTION\n")
                f.write("="*60 + "\n")
                f.write(order_section if order_section else "NOT FOUND")
                f.write("\n\n")
                if player_from_table:
                    f.write("="*60 + "\n")
                    f.write("FOUND IN TABLE\n")
                    f.write("="*60 + "\n")
                    f.write(f"Name: {player_from_table[0]}\n")
                    f.write(f"Year: {player_from_table[1]}\n")
                    f.write(f"Sport: {player_from_table[2]}\n")
                    f.write(f"Row text: {player_from_table[3]}\n")
            logger.info(f"✓ Saved debug info to {debug_file}")
        except Exception as e:
            logger.error(f"Failed to save debug file: {e}")
        
        # Try patterns on order section
        player_from_text = None
        
        # Very specific patterns for the exact format we're seeing
        patterns = [
            # Pattern 1: "1Sophia Roop2025 Pines Volleyball"
            r'\d+([A-Z][a-z]+\s+[A-Z][a-z]+)(\d{4})\s*[Pp]ines\s+(\w+)',
            # Pattern 2: With spaces "1 Sophia Roop 2025 Pines Volleyball"
            r'\d+\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(\d{4})\s+[Pp]ines\s+(\w+)',
            # Pattern 3: No number prefix
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(\d{4})\s*[Pp]ines\s*(\w+)',
            # Pattern 4: Very lenient
            r'([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\s*(\d{4}).*?[Pp]ines.*?(volleyball|soccer|basketball|baseball|softball)',
        ]
        
        for i, pattern in enumerate(patterns, 1):
            matches = list(re.finditer(pattern, order_section, re.IGNORECASE))
            logger.info(f"  Pattern {i}: Found {len(matches)} potential matches")
            
            for match in matches:
                name = match.group(1).strip()
                year = match.group(2)
                sport = match.group(3).strip().lower()
                
                # Validate name
                invalid_keywords = ['thank', 'signing', 'order', 'total', 'balance', 'amount', 'details', 'date']
                if any(keyword in name.lower() for keyword in invalid_keywords):
                    logger.info(f"    ✗ Rejected '{name}' (contains invalid keyword)")
                    continue
                
                if len(name.split()) < 2:
                    logger.info(f"    ✗ Rejected '{name}' (less than 2 words)")
                    continue
                
                logger.info(f"  ✓ Valid match: {name} - {year} - {sport}")
                player_from_text = (name, year, sport)
                break
            
            if player_from_text:
                break
        
        # Use whichever method found a player
        player_info = player_from_table or player_from_text
        
        if player_info:
            player_name = player_info[0]
            year = player_info[1]
            sport = player_info[2]
            
            logger.info("\n" + "="*60)
            logger.info(f"✓✓✓ SUCCESSFULLY PARSED ✓✓✓")
            logger.info(f"  Player: {player_name}")
            logger.info(f"  Year: {year}")
            logger.info(f"  Sport: {sport}")
            logger.info("="*60 + "\n")
            
            # Extract grade info
            division_info = None
            grade_patterns = [
                r'(\d+(?:st|nd|rd|th)/\d+(?:st|nd|rd|th)\s+[Gg]rade)',
                r'([Gg]rade\s+\d+)',
                r'(K-\d+)',
                r'([Kk]indergarten)',
            ]
            for grade_pattern in grade_patterns:
                division_match = re.search(grade_pattern, full_text, re.IGNORECASE)
                if division_match:
                    division_info = division_match.group(1)
                    logger.info(f"✓ Found grade info: {division_info}")
                    break
            
            # Create/update player
            division = "Waiting Room"
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
                    logger.info(f"✓ Added new registration for {player_name}")
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
                logger.info(f"✓ Created new player {player_name}")
            
            logger.info("="*60)
            logger.info("Processing inbound email - SUCCESS")
            logger.info("="*60)
        else:
            logger.error("\n" + "="*60)
            logger.error("✗✗✗ PARSING FAILED ✗✗✗")
            logger.error("Could not extract player information")
            logger.error(f"Check debug file: {debug_file}")
            logger.error("="*60 + "\n")
            
    except Exception as e:
        logger.error("="*60)
        logger.error(f"✗✗✗ ERROR PROCESSING EMAIL ✗✗✗")
        logger.error(f"Exception: {e}", exc_info=True)
        logger.error("="*60)
        db.rollback()

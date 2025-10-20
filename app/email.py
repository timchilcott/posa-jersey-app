import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def parse_posa_email(email_body: str, db):
    """
    Enhanced parser for POSA Sports Association emails.
    Handles the format: "1Sophia Roop2025 Pines Volleyball - 3rd/4th Grade"
    """
    logger.info("=" * 80)
    logger.info("PROCESSING INBOUND EMAIL - START")
    logger.info("=" * 80)
    
    try:
        # Parse email
        import email
        msg = email.message_from_string(email_body)
        
        # Extract parent email
        parent_email = extract_parent_email(email_body, msg)
        logger.info(f"✓ Parent email: {parent_email}")
        
        # Get HTML content
        html_content = get_html_content(msg, email_body)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract order metadata
        order_number, order_date = extract_order_metadata(soup)
        if order_number:
            logger.info(f"✓ Order number: {order_number}")
        if order_date:
            logger.info(f"✓ Order date: {order_date}")
        
        # Get text for parsing
        full_text = soup.get_text(separator=' ', strip=True)
        
        # Extract Order Details section
        order_section = extract_order_section(full_text)
        
        if not order_section:
            logger.error("✗ Could not find Order Details section")
            return
        
        logger.info("\n" + "=" * 80)
        logger.info("ORDER DETAILS SECTION")
        logger.info("=" * 80)
        logger.info(order_section[:500])
        logger.info("=" * 80 + "\n")
        
        # Parse player information
        players = parse_players_from_order(order_section)
        
        if not players:
            logger.error("✗ No players found in order")
            return
        
        # Process each player
        for player_data in players:
            process_player(player_data, parent_email, order_number, order_date, db)
            
        logger.info("✓ Email processing complete")
        
    except Exception as e:
        logger.error(f"✗ Error processing email: {e}", exc_info=True)
        db.rollback()


def extract_parent_email(email_body: str, msg) -> str:
    """Extract parent email from forwarded email or headers."""
    # Try to find forwarded To: field
    forwarded_match = re.search(r'>\s*To:\s*([\w\.-]+@[\w\.-]+\.\w+)', email_body)
    if forwarded_match:
        return forwarded_match.group(1)
    
    # Try email header
    to_header = msg.get('To', '')
    if to_header:
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
        if email_match:
            return email_match.group(0)
    
    return "unknown@example.com"


def get_html_content(msg, email_body: str) -> str:
    """Extract HTML content from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            charset = msg.get_content_charset() or "utf-8"
            return msg.get_payload(decode=True).decode(charset, errors="replace")
    
    return email_body


def extract_order_metadata(soup):
    """Extract order number and date from the email."""
    text = soup.get_text()
    
    # Order number
    order_number = None
    order_match = re.search(r'Order\s*No:?\s*(\d+)', text, re.IGNORECASE)
    if order_match:
        order_number = order_match.group(1)
    
    # Order date
    order_date = None
    date_match = re.search(r'Order Date:[\s\w]+(\w{3}\s+\d{1,2},\s+\d{4})', text)
    if date_match:
        try:
            order_date = datetime.strptime(date_match.group(1), '%b %d, %Y')
        except:
            pass
    
    return order_number, order_date


def extract_order_section(full_text: str) -> str:
    """Extract the Order Details section from the full email text."""
    match = re.search(
        r'Order Details:(.{50,1000}?)(?:Total:|Program Info:|Division Price:|$)',
        full_text,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return full_text


def parse_players_from_order(order_section: str) -> list:
    """
    Parse player information from the Order Details section.
    Handles format: "1Sophia Roop2025 Pines Volleyball - 3rd/4th Grade"
    """
    players = []
    
    # Pattern 1: Handles standard POSA format with grade
    # Format: [digit][Name][Year] Pines [Sport] - [Grade]
    pattern1 = r'\d+([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(\d{4})\s+Pines\s+(\w+)\s*-\s*([^$]+?)(?=\$|$)'
    
    # Pattern 2: Without grade info
    # Format: [digit][Name][Year] Pines [Sport]
    pattern2 = r'\d+([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(\d{4})\s+Pines\s+(\w+)'
    
    # Pattern 3: Case-insensitive sport matching
    # Format: [Name] [Year] Pines [Sport]
    pattern3 = r'([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\s+(\d{4})\s+Pines\s+(volleyball|soccer|basketball|baseball|softball|flag)'
    
    patterns = [
        (pattern1, "with grade"),
        (pattern2, "without grade"),
        (pattern3, "case-insensitive")
    ]
    
    for pattern, description in patterns:
        logger.info(f"Testing pattern: {description}")
        matches = list(re.finditer(pattern, order_section, re.IGNORECASE))
        logger.info(f"  Found {len(matches)} matches")
        
        for i, match in enumerate(matches, 1):
            name = match.group(1).strip()
            year = match.group(2)
            sport = match.group(3).strip().lower()
            
            # Extract grade if available (pattern1)
            grade = None
            if len(match.groups()) > 3:
                grade = match.group(4).strip()
            
            logger.info(f"  Match {i}: '{name}' | {year} | {sport} | {grade or 'no grade'}")
            
            # Validate
            if not is_valid_player_name(name):
                logger.info(f"    ✗ Rejected (invalid name)")
                continue
            
            if not is_valid_year(year):
                logger.info(f"    ✗ Rejected (invalid year)")
                continue
            
            logger.info(f"    ✓ VALID!")
            
            players.append({
                'name': name,
                'year': year,
                'sport': sport,
                'grade': grade
            })
            break
        
        if players:
            break
    
    return players


def is_valid_player_name(name: str) -> bool:
    """Validate that the name is legitimate."""
    invalid_keywords = ['thank', 'signing', 'order', 'total', 'balance', 'amount', 
                        'division', 'price', 'volunteer', 'fee']
    
    name_lower = name.lower()
    if any(kw in name_lower for kw in invalid_keywords):
        return False
    
    if len(name.split()) < 2:
        return False
    
    return True


def is_valid_year(year: str) -> bool:
    """Validate that the year is reasonable."""
    try:
        year_int = int(year)
        current_year = datetime.now().year
        return current_year - 20 <= year_int <= current_year + 5
    except:
        return False


def process_player(player_data: dict, parent_email: str, order_number: str, 
                   order_date, db):
    """Create or update player and registration in database."""
    from app.models import Player, Registration
    from app.email import normalize_division
    
    name = player_data['name']
    year = player_data['year']
    sport = player_data['sport']
    grade = player_data.get('grade')
    
    # Determine division from grade or default
    if grade:
        division = parse_division_from_grade(grade)
    else:
        division = "Waiting Room"
    
    logger.info(f"Processing player: {name} ({year} {sport}) - Division: {division}")
    
    # Check if player exists
    existing_player = db.query(Player).filter(Player.full_name == name).first()
    
    if existing_player:
        # Check if registration exists
        existing_reg = db.query(Registration).filter(
            Registration.player_id == existing_player.id,
            Registration.sport == sport,
            Registration.season == year
        ).first()
        
        if existing_reg:
            logger.info(f"  Registration already exists")
            if not existing_reg.order_number and order_number:
                existing_reg.order_number = order_number
                existing_reg.order_date = order_date
                db.commit()
                logger.info("  ✓ Updated order info")
        else:
            # Create new registration
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
            logger.info(f"  ✓ Added new registration")
    else:
        # Create new player
        new_player = Player(
            full_name=name,
            parent_email=parent_email,
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
        logger.info(f"  ✓ Created new player and registration")


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

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

# Promo code mapping based on number of registrations in a single email
PROMO_CODES = {
    1: "Pines1Player",
    2: "Pines2Players",
    3: "Pines3Players",
    4: "Pines4Players",
    5: "Pines5Players",
    6: "Pines6Players",
    7: "Pines7Players",
}

# URL for ordering uniforms
UNIFORM_ORDER_URL = "https://treblemade.com/search?q=pines&sort_by=relevance"

# Address that should be CC'd on all outbound emails
DEFAULT_CC_EMAIL = "tim@posasports.org"

# Canonical division definitions and normalization mapping
DIVISION_ORDER = {
    "U4": 0,
    "U6": 1,
    "U8": 2,
    "U10": 3,
    "U12": 4,
    "U14": 5,
    "Pend Oreille Pines (High School Club Team)": 6,
}
DIVISION_ALIASES = {
    "UNDER4": "U4",
    "UNDER6": "U6",
    "UNDER8": "U8",
    "UNDER10": "U10",
    "UNDER12": "U12",
    "UNDER14": "U14",
    "HIGHSCHOOL": "Pend Oreille Pines (High School Club Team)",
    "HS": "Pend Oreille Pines (High School Club Team)",
    "PENDOREILLEPINESHIGHSCHOOLCLUBTEAM": "Pend Oreille Pines (High School Club Team)",
}


def normalize_division(raw: str) -> str:
    """Map various division strings to canonical form."""
    key = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    division = DIVISION_ALIASES.get(key, key)
    if division not in DIVISION_ORDER:
        logger.warning("Unknown division '%s', defaulting to 'Unknown'", raw)
        return "Unknown"
    return division


def _plain_text_from_html(html: str) -> str:
    """Derive a plain-text version of HTML content."""
    return BeautifulSoup(html, "html.parser").get_text("\n")


def send_confirmation_email(to_email, players, promo_code=None, registrations=None, db=None):
    """Send a registration confirmation email with jersey info for standard divisions."""
    from .models import EmailTemplate
    
    # Get template from database
    template = None
    if db:
        template = db.query(EmailTemplate).filter(EmailTemplate.name == "standard_confirmation").first()
    
    # Build player list HTML
    players_html = "\n".join(
        f"<p>Player: {p['name']} (#{p['jersey_number']})</p>" for p in players
    )
    
    # Use template if available, otherwise use default
    if template:
        subject = template.subject
        html = template.body_html
        # Replace placeholders
        html = html.replace('{player_list}', players_html)
        html = html.replace('{promo_code}', promo_code if promo_code else '')
        html = html.replace('{uniform_url}', UNIFORM_ORDER_URL)
    else:
        # Fallback to default
        promo_html = f"<p>Promo Code: {promo_code}</p>" if promo_code else ""
        subject = "Jersey Numbers and Uniform Info for Your Player(s)"
        html = (
            "<p>Thanks for signing up for soccer with the Pend Oreille Pines. We're excited to have your family with us this season!</p>"
            "<p>Here's the jersey info for your player(s):</p>"
            f"{players_html}"
            f"{promo_html}"
            f"<p>Order your jerseys here:<br><a href=\"{UNIFORM_ORDER_URL}\">{UNIFORM_ORDER_URL}</a></p>"
            "<p>Only the reversible Pines jersey is required for games. You're welcome to add Pines-branded black shorts and socks to your order, or use your own. Any plain black shorts and socks are just fine as long as they don't have other team logos or colors.</p>"
            "<p>If your family is in a position to purchase the jerseys without using the promo codes, it helps us stretch our nonprofit funds to support other families and improve the program. But either way, jerseys are covered and we're thrilled to have your kids on the field.</p>"
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
        logger.debug(
            "SendGrid response status=%s body=%s headers=%s",
            response.status_code,
            response.body,
            response.headers,
        )
        if registrations and db and 200 <= response.status_code < 300:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    except Exception as e:
        logger.error("Error sending confirmation email: %s", e)


def send_pines_confirmation_email(to_email, players, registrations=None, db=None):
    """Send a registration confirmation email for Pend Oreille Pines High School Club Team."""
    from .models import EmailTemplate
    
    # Get template from database
    template = None
    if db:
        template = db.query(EmailTemplate).filter(EmailTemplate.name == "pines_confirmation").first()
    
    # Build player list HTML
    players_html = "\n".join(
        f"<p>{p['name']}<br>Jersey Number: {p['jersey_number']}</p>" for p in players
    )
    
    # Use template if available, otherwise use default
    if template:
        subject = template.subject
        html = template.body_html
        # Replace placeholders
        html = html.replace('{player_list}', players_html)
        html = html.replace('{uniform_url}', UNIFORM_ORDER_URL)
    else:
        # Fallback to default
        subject = "Jersey Numbers and Uniform Info for Your Player(s)"
        html = (
            "<p>Thanks for registering with the Pend Oreille Pines High School Club Team. We're looking forward to a strong season ahead.</p>"
            "<p>Here's the jersey info for your player(s):</p>"
            f"{players_html}"
            f"<p>Order your full kit here:<br><a href=\"{UNIFORM_ORDER_URL}\">{UNIFORM_ORDER_URL}</a></p>"
            "<p><strong>Uniform Requirements:</strong><br>All High School Club Team players are required to wear the full Pines kit:<br>• Reversible Pines jersey<br>• Pines black shorts<br>• Pines black socks</p>"
            "<p>Please complete your order as soon as possible to ensure everything arrives before the first match. Promo codes are not used for this team, as club players are responsible for purchasing their full kits.</p>"
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
        logger.debug(
            "SendGrid response status=%s body=%s headers=%s",
            response.status_code,
            response.body,
            response.headers,
        )
        if registrations and db and 200 <= response.status_code < 300:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    except Exception as e:
        logger.error("Error sending pines confirmation email: %s", e)

# Utility for capturing raw inbound emails
def save_inbound_email(email_body: str, filename: str | None = None) -> None:
    """Persist the raw inbound email to a file for debugging."""
    root_dir = os.path.dirname(os.path.dirname(__file__))
    if not filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"captured_email_{timestamp}.txt"
    path = os.path.join(root_dir, filename)
    try:
        with open(path, "w") as f:
            f.write(email_body)
        logger.info("Saved inbound email to %s", path)
    except Exception as e:
        logger.error("Failed to save inbound email: %s", e)

def process_inbound_email(email_body: str, db):
    logger.info("Processing inbound email")

    msg = email.message_from_string(email_body)
    text_content = None
    html_content = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                text_content = part.get_payload(decode=True).decode(charset, errors="replace")
                break
        if text_content is None:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    charset = part.get_content_charset() or "utf-8"
                    html_content = part.get_payload(decode=True).decode(charset, errors="replace")
                    text_content = BeautifulSoup(html_content, "html.parser").get_text()
                    break
    else:
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            text_content = msg.get_payload(decode=True).decode(charset, errors="replace")
        elif msg.get_content_type() == "text/html":
            charset = msg.get_content_charset() or "utf-8"
            html_content = msg.get_payload(decode=True).decode(charset, errors="replace")
            text_content = BeautifulSoup(html_content, "html.parser").get_text()

    if text_content is None or not re.search(r"Name:\s*", text_content, re.IGNORECASE):
        text_content = email_body

    # Clean up formatting issues
    text_content = text_content.replace("\r\n", "\n").replace("=\n", "").strip()

    lines = text_content.splitlines()

    # Split by lines and chunk into blocks per registrant
    registrant_blocks = []
    current_block = []

    for line in lines:
        if line.strip() == "":
            if current_block:
                registrant_blocks.append(current_block)
                current_block = []
        else:
            current_block.append(line)

    if current_block:
        registrant_blocks.append(current_block)

    parsed_regs = []

    for block in registrant_blocks:
        full_text = "\n".join(block)

        # Skip adult leagues and camps
        if "Adult League Softball" in full_text or "Camp" in full_text:
            logger.info("Skipping non-youth program")
            continue

        try:
            name_match = re.search(r"Name:\s*(.+)", full_text, re.IGNORECASE)
            program_match = re.search(r"Program:\s*(.+)", full_text, re.IGNORECASE)
            division_match = re.search(r"Division:\s*(.+)", full_text, re.IGNORECASE)
            parent_email_match = re.search(r"Parent Email:\s*(.+)", full_text, re.IGNORECASE)
            order_number_match = re.search(r"Order Number:\s*(.+)", full_text, re.IGNORECASE)
            order_date_match = re.search(r"Order Date:\s*(.+)", full_text, re.IGNORECASE)

            missing = [key for key, match in {
                "Name": name_match,
                "Program": program_match,
                "Parent Email": parent_email_match,
            }.items() if not match]

            if missing:
                logger.warning("Skipping entry, missing: %s", ", ".join(missing))
                continue

            full_name = name_match.group(1).strip()
            program = program_match.group(1).strip()
            division_raw = division_match.group(1).strip() if division_match else ""
            division = normalize_division(division_raw)
            if division == "Unknown" and "high school" in program.lower():
                division = "Pend Oreille Pines (High School Club Team)"
            parent_email = parent_email_match.group(1).strip()
            order_number = order_number_match.group(1).strip() if order_number_match else None
            order_date = datetime.strptime(order_date_match.group(1).strip(), "%B %d, %Y") if order_date_match else None

            sport = "unknown"
            season = "unknown"

            parts = program.lower().split()
            if "fall" in parts:
                season = "fall"
            elif "spring" in parts:
                season = "spring"
            elif "summer" in parts:
                season = "summer"
            elif "winter" in parts:
                season = "winter"

            for s in ["soccer", "basketball", "baseball", "softball", "volleyball", "flag"]:
                if s in parts:
                    sport = s
                    break

            parsed_regs.append({
                "full_name": full_name,
                "program": program,
                "division": division,
                "parent_email": parent_email,
                "order_number": order_number,
                "order_date": order_date,
                "sport": sport,
                "season": season,
            })

        except Exception as e:
            logger.error("Error processing registrant block: %s", e)

    if not parsed_regs and html_content:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            order_table = None
            for table in soup.find_all("table"):
                if table.find(string=re.compile("Order Details", re.IGNORECASE)):
                    order_table = table
                    break

            if order_table:
                order_number = None
                order_date = None

                for row in order_table.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    header = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if re.search("Order Number", header, re.IGNORECASE):
                        order_number = value
                    elif re.search("Order Date", header, re.IGNORECASE):
                        try:
                            order_date = datetime.strptime(value, "%B %d, %Y")
                        except Exception:
                            order_date = None

                for row in order_table.find_all("tr"):
                    spans = row.find_all("span")
                    texts = [s.get_text(strip=True) for s in spans]
                    if not texts:
                        continue

                    # Remove leading timestamp/date spans
                    date_pattern = (
                        r'(?:[A-Za-z]{3,9},\s*)?'
                        r'(?:\d{1,2}/\d{1,2}/\d{2,4}|'
                        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,\s*|\s+)\d{4})'
                        r'(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM))?'
                    )
                    while texts and (
                        re.search(date_pattern, texts[0], re.IGNORECASE)
                        or re.search(r"\d{1,2}:\d{2}\s*(AM|PM)", texts[0], re.IGNORECASE)
                    ):
                        texts.pop(0)

                    # Remove any leading "Jersey Number" span and an immediate numeric value
                    if texts and texts[0].lower().startswith("jersey number"):
                        texts.pop(0)
                        if texts and re.fullmatch(r"\d+", texts[0]):
                            texts.pop(0)

                    # Remove any leading "Jersey Number" spans and following numeric value
                    jersey_label_removed = False
                    while texts and texts[0].lower().startswith("jersey number"):
                        texts.pop(0)
                        jersey_label_removed = True
                    if jersey_label_removed and texts and re.match(r"^\d+$", texts[0]):
                        texts.pop(0)

                    # Skip rows where the first span looks like a price or lacks letters
                    currency_pattern = r"^\$?[\d,]+(?:\.\d{2})?(?:\s*[:A-Za-z].*)?$"
                    if texts and (
                        re.match(currency_pattern, texts[0])
                        or not re.search(r"[A-Za-z]", texts[0])
                    ):
                        continue

                    if len(texts) < 2:
                        continue

                    full_name, prog_div = texts[0], texts[1]

                    # Skip rows that don't look like player entries
                    if not prog_div:
                        continue
                    if re.search(r"Order (Date|Number)", full_name, re.IGNORECASE):
                        continue
                    if re.search(date_pattern, full_name, re.IGNORECASE) or re.search(
                        r"\d{1,2}:\d{2}\s*(AM|PM)", full_name, re.IGNORECASE
                    ):
                        continue

                    if " - " in prog_div:
                        program, division = [p.strip() for p in prog_div.split(" - ", 1)]
                    else:
                        program = prog_div.strip()
                        division = ""

                    if not full_name or not program:
                        continue

                    division = normalize_division(division)
                    if division == "Unknown" and "high school" in program.lower():
                        division = "Pend Oreille Pines (High School Club Team)"
                    parent_email = msg.get("To")

                    sport = "unknown"
                    season = "unknown"
                    parts = program.lower().split()
                    if "fall" in parts:
                        season = "fall"
                    elif "spring" in parts:
                        season = "spring"
                    elif "summer" in parts:
                        season = "summer"
                    elif "winter" in parts:
                        season = "winter"

                    for s in ["soccer", "basketball", "baseball", "softball", "volleyball", "flag"]:
                        if s in parts:
                            sport = s
                            break

                    parsed_regs.append({
                        "full_name": full_name,
                        "program": program,
                        "division": division,
                        "parent_email": parent_email,
                        "order_number": order_number,
                        "order_date": order_date,
                        "sport": sport,
                        "season": season,
                    })
        except Exception as e:
            logger.error("Error parsing order details table: %s", e)

    promo_code = PROMO_CODES.get(len(parsed_regs))

    for entry in parsed_regs:
        player = db.query(Player).filter_by(full_name=entry["full_name"]).first()

        if not player:
            jersey_number = assign_jersey_number(db, entry["division"])
            player = Player(
                full_name=entry["full_name"],
                parent_email=entry["parent_email"],
                jersey_number=jersey_number,
            )
            db.add(player)
            db.commit()
            db.refresh(player)

        existing_reg = db.query(Registration).filter_by(
            player_id=player.id,
            sport=entry["sport"],
            season=entry["season"],
        ).first()

        if not existing_reg:
            reg = Registration(
                player_id=player.id,
                program=entry["program"],
                division=entry["division"],
                sport=entry["sport"],
                season=entry["season"],
                order_number=entry["order_number"],
                order_date=entry["order_date"],
                confirmation_sent=False,
            )
            db.add(reg)
            db.commit()

            # Auto email sending disabled. Uncomment to enable.
            # send_confirmation_email(
            #     player.parent_email,
            #     [{"name": player.full_name, "jersey_number": player.jersey_number}],
            #     "https://your-order-url.com",
            #     [reg],
            #     db,
            #     promo_code=promo_code,
            # )
        else:
            existing_reg.division = entry["division"]
            existing_reg.program = entry["program"]
            existing_reg.order_number = entry["order_number"]
            existing_reg.order_date = entry["order_date"]
            db.commit()
            logger.info(
                "Updated registration for %s to %s in %s %s",
                player.full_name,
                entry["division"],
                entry["sport"],
                entry["season"],
            )

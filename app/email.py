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
# Constants
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

UNIFORM_ORDER_URL = "https://treblemade.com/products/pines-soccer-reversible-jersey?_pos=1&_sid=0fa41b461&_ss=r"
DEFAULT_CC_EMAIL = "tim@posasports.org"

DIVISION_ORDER = {
    "U3": -1,  # POSA local override
    "U4": 0,
    "U6": 1,
    "U8": 2,
    "U10": 3,
    "U12": 4,
    "U14": 5,
    "Pend Oreille Pines (High School Club Team)": 6,
}

DIVISION_ALIASES = {
    "U3": "U3",
    "UNDER3": "U3",
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

# ---------------------------------------------------------------------
# Division normalization
# ---------------------------------------------------------------------
def normalize_division(raw: str, birth_year: int | None = None) -> str:
    """Normalize division names and apply POSA 2022 → U3 override."""
    key = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()

    if key in DIVISION_ALIASES:
        return DIVISION_ALIASES[key]

    if birth_year == 2022:
        return "U3"

    division = DIVISION_ALIASES.get(key, key)
    if division not in DIVISION_ORDER:
        logger.warning("Unknown division '%s', defaulting to 'Unknown'", raw)
        return "Unknown"
    return division

# ---------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------
def _plain_text_from_html(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text("\n")

# ---------------------------------------------------------------------
# Outbound mailers
# ---------------------------------------------------------------------
def send_confirmation_email(to_email, players, promo_code=None, registrations=None, db=None):
    from .models import EmailTemplate
    template = db.query(EmailTemplate).filter(EmailTemplate.name == "standard_confirmation").first() if db else None
    players_html = "\n".join(
        f"<p>Player: {p['name']} (#{p['jersey_number']}) - {p['sport']}</p>" for p in players
    )
    unique_sports = list(set(p['sport'] for p in players))
    sport_text = ", ".join(sorted(unique_sports)) if unique_sports else "Unknown"

    if template:
        subject = template.subject
        html = template.body_html
        html = html.replace("{player_list}", players_html)
        html = html.replace("{promo_code}", promo_code if promo_code else "")
        html = html.replace("{uniform_url}", UNIFORM_ORDER_URL)
        html = html.replace("{sport}", sport_text)
    else:
        promo_html = f"<p>Promo Code: {promo_code}</p>" if promo_code else ""
        subject = "Jersey Numbers and Uniform Info for Your Player(s)"
        html = (
            "<p>Thanks for signing up for soccer with the Pend Oreille Pines. We're excited to have your family with us this season!</p>"
            f"{players_html}"
            f"{promo_html}"
            f"<p>Order your jerseys here:<br><a href='{UNIFORM_ORDER_URL}'>{UNIFORM_ORDER_URL}</a></p>"
            "<p>Only the reversible Pines jersey is required for games. Any plain black shorts and socks are fine as long as they don't have other team logos or colors.</p>"
            "<p>If your family can purchase jerseys without using promo codes, it helps stretch our nonprofit funds — but either way, jerseys are covered and we’re thrilled to have your kids on the field.</p>"
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
        logger.debug("SendGrid response %s", response.status_code)
        if registrations and db and 200 <= response.status_code < 300:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    except Exception as e:
        logger.error("Error sending confirmation email: %s", e)

def send_pines_confirmation_email(to_email, players, registrations=None, db=None):
    from .models import EmailTemplate
    template = db.query(EmailTemplate).filter(EmailTemplate.name == "pines_confirmation").first() if db else None
    players_html = "\n".join(
        f"<p>{p['name']}<br>Jersey Number: {p['jersey_number']}<br>Sport: {p['sport']}</p>" for p in players
    )
    unique_sports = list(set(p['sport'] for p in players))
    sport_text = ", ".join(sorted(unique_sports)) if unique_sports else "Unknown"

    if template:
        subject = template.subject
        html = template.body_html
        html = html.replace("{player_list}", players_html)
        html = html.replace("{uniform_url}", UNIFORM_ORDER_URL)
        html = html.replace("{sport}", sport_text)
    else:
        subject = "Jersey Numbers and Uniform Info for Your Player(s)"
        html = (
            "<p>Thanks for registering with the Pend Oreille Pines High School Club Team. We're looking forward to a strong season ahead.</p>"
            f"{players_html}"
            f"<p>Order your full kit here:<br><a href='{UNIFORM_ORDER_URL}'>{UNIFORM_ORDER_URL}</a></p>"
            "<p><strong>Uniform Requirements:</strong> Reversible jersey, Pines black shorts, and Pines black socks.</p>"
            "<p>Club players purchase their own full kits. Promo codes are not used for this division.</p>"
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
        logger.debug("SendGrid response %s", response.status_code)
        if registrations and db and 200 <= response.status_code < 300:
            for reg in registrations:
                reg.confirmation_sent = True
            db.commit()
    except Exception as e:
        logger.error("Error sending pines confirmation email: %s", e)

# ---------------------------------------------------------------------
# Inbound email capture and parsing (restored)
# ---------------------------------------------------------------------
def save_inbound_email(email_body: str, filename: str | None = None) -> None:
    root_dir = os.path.dirname(os.path.dirname(__file__))
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"captured_email_{timestamp}.txt"
    path = os.path.join(root_dir, filename)
    try:
        with open(path, "w") as f:
            f.write(email_body)
        logger.info("Saved inbound email to %s", path)
    except Exception as e:
        logger.error("Failed to save inbound email: %s", e)

def process_inbound_email(email_body: str, db):
    """Full inbound email processing logic (restored from your prior version)."""
    logger.info("Processing inbound email")

    msg = email.message_from_string(email_body)
    text_content = None
    html_content = None

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
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

    if not text_content:
        text_content = email_body

    text_content = text_content.replace("\r\n", "\n").replace("=\n", "").strip()
    lines = text_content.splitlines()

    registrant_blocks, current_block = [], []
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
        if "Adult League Softball" in full_text or "Camp" in full_text:
            continue
        try:
            name_match = re.search(r"Name:\s*(.+)", full_text, re.IGNORECASE)
            program_match = re.search(r"Program:\s*(.+)", full_text, re.IGNORECASE)
            division_match = re.search(r"Division:\s*(.+)", full_text, re.IGNORECASE)
            parent_email_match = re.search(r"Parent Email:\s*(.+)", full_text, re.IGNORECASE)
            if not name_match or not program_match or not parent_email_match:
                continue
            full_name = name_match.group(1).strip()
            program = program_match.group(1).strip()
            division_raw = division_match.group(1).strip() if division_match else ""
            division = normalize_division(division_raw)
            if division == "Unknown" and "high school" in program.lower():
                division = "Pend Oreille Pines (High School Club Team)"
            parent_email = parent_email_match.group(1).strip()
            sport, season = "unknown", "unknown"
            parts = program.lower().split()
            for s in ["fall", "spring", "summer", "winter"]:
                if s in parts:
                    season = s
            for s in ["soccer", "basketball", "baseball", "softball", "volleyball", "flag"]:
                if s in parts:
                    sport = s
            parsed_regs.append({
                "full_name": full_name,
                "program": program,
                "division": division,
                "parent_email": parent_email,
                "sport": sport,
                "season": season,
            })
        except Exception as e:
            logger.error("Error processing registrant block: %s", e)

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
                confirmation_sent=False,
            )
            db.add(reg)
            db.commit()

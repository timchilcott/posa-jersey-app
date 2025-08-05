import os
import re
import email
from bs4 import BeautifulSoup
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .models import Player, Registration
from .services.assign import assign_jersey_number

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

# Canonical division definitions and normalization mapping
DIVISION_ORDER = {
    "U4": 0,
    "U6": 1,
    "U8": 2,
    "U10": 3,
    "U12": 4,
    "U14": 5,
    "High School": 6,
    "Pend Oreille Pines (High School Club Team)": 7,
}
DIVISION_ALIASES = {
    "UNDER4": "U4",
    "UNDER6": "U6",
    "UNDER8": "U8",
    "UNDER10": "U10",
    "UNDER12": "U12",
    "UNDER14": "U14",
    "HIGHSCHOOL": "High School",
    "HS": "High School",
    "PENDOREILLEPINESHIGHSCHOOLCLUBTEAM": "Pend Oreille Pines (High School Club Team)",
}


def normalize_division(raw: str) -> str:
    """Map various division strings to canonical form."""
    key = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    division = DIVISION_ALIASES.get(key, key)
    if division not in DIVISION_ORDER:
        print(f"⚠️ Unknown division '{raw}', defaulting to 'Unknown'")
        return "Unknown"
    return division

print("📬 Loaded email.py")

# Simplified for local/dev use – no actual email sending, just update flag
def send_confirmation_email(to_email, players, registrations=None, db=None):
    body = (
        "Thanks for signing up for soccer with the Pend Oreille Pines. We're excited to have your family with us this season!\n\n"
        "Here's the jersey info for your player(s):\n\n"
    )

    for p in players:
        body += (
            f"{p['name']}\n"
            f"Jersey Number: {p['jersey_number']}\n"
            f"Promo Code: {p['promo_code']}\n\n"
        )

    body += (
        "Order your jerseys here:\n"
        "https://treblemade.com/search?q=pines&sort_by=relevance\n\n"
        "Only the reversible Pines jersey is required for games. You're welcome to add Pines-branded black shorts and socks to your order, or use your own. Any plain black shorts and socks are just fine as long as they don't have other team logos or colors.\n\n"
        "If your family is in a position to purchase the jerseys without using the promo codes, it helps us stretch our nonprofit funds to support other families and improve the program. But either way, jerseys are covered and we're thrilled to have your kids on the field.\n\n"
        "—\n"
        "Tim Chilcott\n"
        "President - POSA\n"
        "🌲 Pines stand tall.\n"
        "❤️ The heart of sports starts with us."
    )

    body = body.strip()

    message = Mail(
        from_email="noreply@posasports.org",
        to_emails=to_email,
        subject="Your POSA Jersey Numbers",
        plain_text_content=body,
    )
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception:
        print(f"[DEV MODE] Email to {to_email}:\n{body}")

    if registrations and db:
        for reg in registrations:
            reg.confirmation_sent = True
        db.commit()

# Optional: uncomment to send actual emails in production
# def send_confirmation_email(to_email, player_name, jersey_number, order_url, registration=None, db=None, promo_code=None):
#     html = f"""
#         <p>Hi {player_name},</p>
#         <p>Your jersey number is <strong>{jersey_number}</strong>.</p>
#     """
#     if promo_code:
#         html += f"<p>Your promo code is <strong>{promo_code}</strong>. Use it during checkout for your free jersey.</p>"
#     html += f'<p>You can order your uniform here: <a href="{order_url}">Order Jersey</a></p>'
#     message = Mail(
#         from_email="noreply@posasports.org",
#         to_emails=to_email,
#         subject="Your POSA Jersey Number",
#         html_content=html,
#     )
#     try:
#         sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
#         response = sg.send(message)
#         print(response.status_code)
#         print(response.body)
#         print(response.headers)
#         if registration and db:
#             registration.confirmation_sent = True
#             db.commit()
#     except Exception as e:
#         print(e)

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
        print(f"📩 Saved inbound email to {path}")
    except Exception as e:
        print(f"❌ Failed to save inbound email: {e}")

def process_inbound_email(email_body: str, db):
    print("📥 Processing inbound email")

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
            print("⏭ Skipping non-youth program")
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
                print(f"❌ Skipping entry, missing: {', '.join(missing)}")
                continue

            full_name = name_match.group(1).strip()
            program = program_match.group(1).strip()
            division_raw = division_match.group(1).strip() if division_match else ""
            division = normalize_division(division_raw)
            if division == "Unknown" and "high school" in program.lower():
                division = "High School"
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
            print(f"❌ Error processing registrant block: {e}")

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
                    if len(spans) >= 2:
                        full_name = spans[0].get_text(strip=True)
                        prog_div = spans[1].get_text(strip=True)
                        if " - " in prog_div:
                            program, division = [p.strip() for p in prog_div.split(" - ", 1)]
                        else:
                            program = prog_div.strip()
                            division = ""
                        division = normalize_division(division)
                        if division == "Unknown" and "high school" in program.lower():
                            division = "High School"
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
            print(f"❌ Error parsing order details table: {e}")

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
            print(
                f"✔ Updated registration for {player.full_name} to {entry['division']} in {entry['sport']} {entry['season']}"
            )

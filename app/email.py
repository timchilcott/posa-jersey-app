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

print("📬 Loaded email.py")

# Simplified for local/dev use – no actual email sending, just update flag
def send_confirmation_email(to_email, player_name, jersey_number, order_url, registration=None, db=None, promo_code=None):
    promo_msg = f" Promo code: {promo_code}" if promo_code else ""
    print(f"[DEV MODE] Skipping sending email to {to_email} for {player_name} (#{jersey_number}){promo_msg}")

    if registration and db:
        registration.confirmation_sent = True
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
                    html = part.get_payload(decode=True).decode(charset, errors="replace")
                    text_content = BeautifulSoup(html, "html.parser").get_text()
                    break
    else:
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            text_content = msg.get_payload(decode=True).decode(charset, errors="replace")
        elif msg.get_content_type() == "text/html":
            charset = msg.get_content_charset() or "utf-8"
            html = msg.get_payload(decode=True).decode(charset, errors="replace")
            text_content = BeautifulSoup(html, "html.parser").get_text()

    if text_content is None:
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
                "Division": division_match,
                "Parent Email": parent_email_match,
            }.items() if not match]

            if missing:
                print(f"❌ Skipping entry, missing: {', '.join(missing)}")
                continue

            full_name = name_match.group(1).strip()
            program = program_match.group(1).strip()
            division = division_match.group(1).strip()
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
            division=entry["division"],
            season=entry["season"],
            sport=entry["sport"],
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
            #     player.full_name,
            #     player.jersey_number,
            #     "https://your-order-url.com",
            #     reg,
            #     db,
            #     promo_code=promo_code,
            # )
        else:
            print(
                f"✔ Registration already exists for {player.full_name} in {entry['division']} {entry['sport']} {entry['season']}"
            )

import os
import re
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .models import Player, Registration
from .services.assign import assign_jersey_number

print("📬 Loaded email.py")

# Simplified for local/dev use – no actual email sending, just update flag
def send_confirmation_email(to_email, player_name, jersey_number, order_url, registration=None, db=None):
    print(f"[DEV MODE] Skipping sending email to {to_email} for {player_name} (#{jersey_number})")

    if registration and db:
        registration.confirmation_sent = True
        db.commit()

# Optional: uncomment to send actual emails in production
"""
def send_confirmation_email(to_email, player_name, jersey_number, order_url, registration=None, db=None):
    message = Mail(
        from_email="noreply@posasports.org",
        to_emails=to_email,
        subject="Your POSA Jersey Number",
        html_content=f"""
        <p>Hi {player_name},</p>
        <p>Your jersey number is <strong>{jersey_number}</strong>.</p>
        <p>You can order your uniform here: <a href="{order_url}">Order Jersey</a></p>
        """
    )
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
        if registration and db:
            registration.confirmation_sent = True
            db.commit()
    except Exception as e:
        print(e)
"""

def process_inbound_email(email_body: str, db):
    print("📥 Processing inbound email")

    # Clean up formatting issues
    email_body = email_body.replace("\r\n", "\n").replace("=\n", "").strip()

    # Split by lines and chunk into blocks per registrant
    lines = email_body.splitlines()
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

    for block in registrant_blocks:
        full_text = "\n".join(block)

        # Skip adult leagues and camps
        if "Adult League Softball" in full_text or "Camp" in full_text:
            print("⏭ Skipping non-youth program")
            continue

        try:
            name_match = re.search(r"Name:\s*(.+)", full_text)
            program_match = re.search(r"Program:\s*(.+)", full_text)
            division_match = re.search(r"Division:\s*(.+)", full_text)
            parent_email_match = re.search(r"Parent Email:\s*(.+)", full_text)
            order_number_match = re.search(r"Order Number:\s*(.+)", full_text)
            order_date_match = re.search(r"Order Date:\s*(.+)", full_text)

            if not all([name_match, program_match, division_match, parent_email_match]):
                print("❌ Skipping incomplete entry")
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

            player = db.query(Player).filter_by(full_name=full_name).first()

            if not player:
                jersey_number = assign_jersey_number(db, division)
                player = Player(full_name=full_name, parent_email=parent_email, jersey_number=jersey_number)
                db.add(player)
                db.commit()
                db.refresh(player)

            existing_reg = db.query(Registration).filter_by(
                player_id=player.id,
                division=division,
                season=season,
                sport=sport
            ).first()

            if not existing_reg:
                reg = Registration(
                    player_id=player.id,
                    program=program,
                    division=division,
                    sport=sport,
                    season=season,
                    order_number=order_number,
                    order_date=order_date,
                    confirmation_sent=False
                )
                db.add(reg)
                db.commit()

                send_confirmation_email(player.parent_email, player.full_name, player.jersey_number, "https://your-order-url.com", reg, db)
            else:
                print(f"✔ Registration already exists for {player.full_name} in {division} {sport} {season}")

        except Exception as e:
            print(f"❌ Error processing registrant block: {e}")

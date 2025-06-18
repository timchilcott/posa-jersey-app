import os
import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Debug: confirm file loads
print("📬 Loaded email.py")

def send_confirmation_email(to_email, player_name, jersey_number, order_url):
    # Email sending is currently disabled.
    print(f"[DEV MODE] Skipping email to {to_email} for {player_name} (#{jersey_number})")

    from_email = os.getenv("FROM_EMAIL")
    api_key = os.getenv("SENDGRID_API_KEY")

    print(f"🧪 FROM_EMAIL={from_email}")
    print(f"🧪 SENDGRID_API_KEY begins with={api_key[:5] if api_key else 'None'}")

    if not from_email or not api_key:
        print("❌ Missing FROM_EMAIL or SENDGRID_API_KEY in environment variables.")
        return

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject="Your POSA Jersey Info",
        html_content=f"""
            <p>Hi there,</p>
            <p><strong>{player_name}</strong> has been assigned jersey number <strong>{jersey_number}</strong>.</p>
            <p>Please order their uniform here:</p>
            <p><a href="{order_url}" target="_blank">{order_url}</a></p>
            <p>If you have any questions, reply to this email.</p>
            <p>🌲 Pines stand tall.</p>
        """
    )

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        print(f"✅ Email sent to {to_email}: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")


def process_inbound_email(raw_email: str, db):
    """
    Basic example to parse raw email text and save a Player to DB.
    You’ll need to adjust regexes to match your actual email format.
    """

    print("📧 Processing inbound email")

    # Example regex patterns — adjust as needed for your email format
    name_match = re.search(r"Player Name:\s*(.+)", raw_email)
    dob_match = re.search(r"Date of Birth:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", raw_email)
    parent_email_match = re.search(r"Parent Email:\s*(\S+@\S+)", raw_email)

    if not name_match or not dob_match or not parent_email_match:
        print("❌ Required data not found in email")
        return

    full_name = name_match.group(1).strip()
    dob = dob_match.group(1).strip()
    parent_email = parent_email_match.group(1).strip()

    print(f"Extracted Player: {full_name}, DOB: {dob}, Parent Email: {parent_email}")

    # Check if player already exists
    existing_player = db.query(Player).filter_by(full_name=full_name, dob=dob).first()
    if existing_player:
        print(f"⚠️ Player {full_name} already exists in DB.")
        return

    # Assign jersey number (you may need to import your assigner here)
    from .services.assign import assign_jersey_number
    jersey_number = assign_jersey_number(dob, db)

    # Create and add new player
    from .models import Player
    new_player = Player(
        full_name=full_name,
        dob=dob,
        parent_email=parent_email,
        jersey_number=jersey_number
    )

    try:
        db.add(new_player)
        db.commit()
        print(f"✅ Added player {full_name} to database with jersey #{jersey_number}")
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to add player: {e}")

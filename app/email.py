import os
import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Debug: confirm file loads
print("📬 Loaded email.py")

def send_confirmation_email(to_email, player_name, jersey_number, order_url):
    # Email sending is currently disabled for development.
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
    Parses the raw inbound email content (like Sports Connect order confirmation)
    and inserts player info into the database.
    """

    print("📧 Processing inbound email")

    # Optional: print full raw email for debugging (comment out if noisy)
    print("---- Raw email start ----")
    print(raw_email)
    print("---- Raw email end ----")

    # Regex to find order lines with player and program info, e.g.:
    # 1 Wells Chilcott2025 Pines Fall Soccer - U6 $25.00 $0.00
    order_line_pattern = re.compile(r"\d+\s+([A-Za-z\s'-]+)(\d{4} Pines Fall Soccer - \w+)", re.MULTILINE)
    matches = order_line_pattern.findall(raw_email)

    if not matches:
        print("❌ No matching order details found")
        return

    # Local imports to avoid circular dependencies
    from .models import Player, Registration
    from .services.assign import assign_jersey_number

    for player_name, program_info in matches:
        player_name = player_name.strip()
        program_info = program_info.strip()

        # Extract division from program_info, e.g., "U6" from "2025 Pines Fall Soccer - U6"
        division_match = re.search(r"- (\w+)$", program_info)
        division = division_match.group(1) if division_match else "Unknown"

        # Assume sport is "soccer"
        sport = "soccer"

        print(f"Extracted Player: {player_name}, Program: {program_info}, Division: {division}")

        # Check if player already exists in DB by full name (improve criteria if needed)
        existing_player = db.query(Player).filter_by(full_name=player_name).first()
        if existing_player:
            print(f"⚠️ Player {player_name} already exists in DB.")
            # Optionally add new registration if necessary
            continue

        # Assign jersey number passing db and division (correct order!)
        jersey_number = assign_jersey_number(db, division)

        # Create Player with dummy DOB (no DOB in email)
        new_player = Player(
            full_name=player_name,
            dob="2000-01-01",
            parent_email=None,  # Update if you can extract from email headers
            jersey_number=jersey_number
        )
        db.add(new_player)
        db.commit()
        db.refresh(new_player)
        print(f"✅ Added player {player_name} with jersey #{jersey_number}")

        # Create registration record
        new_registration = Registration(
            player_id=new_player.id,
            sport=sport,
            division=division
        )
        db.add(new_registration)
        db.commit()
        print(f"✅ Added registration for {sport} {division}")

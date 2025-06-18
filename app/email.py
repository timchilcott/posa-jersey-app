import os
import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Debug: confirm file loads
print("📬 Loaded email.py")

def send_confirmation_email(to_email, player_name, jersey_number, order_url):
    # Email sending is disabled for now
    print(f"[DEV MODE] Skipping sending email to {to_email} for {player_name} (#{jersey_number})")

    # Uncomment below to enable sending
    """
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
        html_content=f'''
            <p>Hi there,</p>
            <p><strong>{player_name}</strong> has been assigned jersey number <strong>{jersey_number}</strong>.</p>
            <p>Please order their uniform here:</p>
            <p><a href="{order_url}" target="_blank">{order_url}</a></p>
            <p>If you have any questions, reply to this email.</p>
            <p>🌲 Pines stand tall.</p>
        '''
    )

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        print(f"✅ Email sent to {to_email}: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
    """

def process_inbound_email(raw_email: str, db):
    """
    Parses the raw inbound email content (like Sports Connect order confirmation)
    and inserts player info into the database.
    """

    print("📧 Processing inbound email")

    # Print full raw email for debugging (optional, comment out later)
    print("---- Raw email start ----")
    print(raw_email)
    print("---- Raw email end ----")

    # Extract parent email from the "To:" field in the email header
    to_email_match = re.search(r"^To:\s*(.*)", raw_email, re.MULTILINE)
    if to_email_match:
        parent_email = to_email_match.group(1).strip()
        print(f"Parent Email: {parent_email}")
    else:
        print("❌ Parent email not found in the 'To' field.")
        return

    # Regex to find order lines with player and program info, e.g.:
    order_line_pattern = re.compile(r"\d+\s+([A-Za-z\s'-]+)(\d{4} Pines Fall Soccer - \w+)", re.MULTILINE)
    matches = order_line_pattern.findall(raw_email)

    if not matches:
        print("❌ No matching order details found")
        return

    # Import here to avoid circular import
    from .models import Player, Registration
    from .services.assign import assign_jersey_number

    for player_name, program_info in matches:
        player_name = player_name.strip()
        program_info = program_info.strip()

        # Extract division from program_info, e.g., U6 from "2025 Pines Fall Soccer - U6"
        division_match = re.search(r"- (\w+)$", program_info)
        division = division_match.group(1) if division_match else "Unknown"

        # We assume sport is "soccer" based on program info structure
        sport = "soccer"

        print(f"Extracted Player: {player_name}, Program: {program_info}, Division: {division}")

        # Check if player exists by full name (you might want to improve uniqueness criteria)
        existing_player = db.query(Player).filter_by(full_name=player_name).first()
        if existing_player:
            print(f"⚠️ Player {player_name} already exists in DB.")
            # Optionally add new registration if needed here
            continue

        # No need for DOB logic here, as it's not required
        # Assign a dummy DOB (if necessary)
        dummy_dob = "2000-01-01"  # Can be removed or adjusted as per your needs

        jersey_number = assign_jersey_number(db, division)

        # Create Player
        new_player = Player(
            full_name=player_name,
            parent_email=parent_email,  # Parent email extracted from 'To' field
            jersey_number=jersey_number
        )
        db.add(new_player)
        db.commit()
        db.refresh(new_player)
        print(f"✅ Added player {player_name} with jersey #{jersey_number}")

        # Create Registration
        new_registration = Registration(
            player_id=new_player.id,
            sport=sport,
            division=division,
            program=program_info,
            season="Fall 2025"
        )
        db.add(new_registration)
        db.commit()
        print(f"✅ Added registration for {sport} {division}")

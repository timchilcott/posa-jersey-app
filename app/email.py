import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Debug: confirm file loads
print("📬 Loaded email.py")

def send_confirmation_email(to_email, player_name, jersey_number, order_url):
    # Email sending is currently disabled.
    print(f"[DEV MODE] Skipping email to {to_email} for {player_name} (#{jersey_number})")


    from_email = os.getenv("FROM_EMAIL")
    api_key = os.getenv("SENDGRID_API_KEY")

    # Debug: Print env variable contents
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

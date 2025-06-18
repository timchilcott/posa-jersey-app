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

    # Regex to find order lines with player and program info, e.g.:
    # 1 Wells Chilcott2025 Pines Fall Soccer - U6 $25.00 $0.00
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

        # Correct call: assign jersey number using db and division
        jersey_number = assign_jersey_number(db, division)

        # Create Player with dummy DOB (since not provided)
        new_player = Player(
            full_name=player_name,
            dob="2000-01-01",
            parent_email=None,  # You can add logic to extract parent email if available
            jersey_number=jersey_number
        )
        db.add(new_player)
        db.commit()
        db.refresh(new_player)
        print(f"✅ Added player {player_name} with jersey #{jersey_number}")

        # Create Registration record for player, sport, division
        new_registration = Registration(
            player_id=new_player.id,
            sport=sport,
            division=division
        )
        db.add(new_registration)
        db.commit()
        print(f"✅ Added registration for {sport} {division}")

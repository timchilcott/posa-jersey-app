from datetime import date, datetime
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Player, Registration

def seed_data():
    db: Session = SessionLocal()

    # Clear existing data
    db.query(Registration).delete()
    db.query(Player).delete()

    sample_data = [
        {
            "full_name": "Jordan Smith",
            "dob": date(2012, 5, 14),
            "parent_email": "jordan.parent@example.com",
            "jersey_number": 10,
            "registrations": [
                {"sport": "Soccer", "season": "Fall 2025"},
                {"sport": "Basketball", "season": "Winter 2025"},
            ],
        },
        {
            "full_name": "Taylor Brown",
            "dob": date(2010, 8, 2),
            "parent_email": "taylor@example.com",
            "jersey_number": 7,
            "registrations": [
                {"sport": "Soccer", "season": "Fall 2025"},
            ],
        },
        {
            "full_name": "Riley Lee",
            "dob": date(2014, 2, 20),
            "parent_email": "riley@example.com",
            "jersey_number": 22,
            "registrations": [
                {"sport": "Baseball", "season": "Summer 2025"},
            ],
        },
        {
            "full_name": "Morgan Davis",
            "dob": date(2013, 11, 9),
            "parent_email": "morgan@example.com",
            "jersey_number": 3,
            "registrations": [],
        },
    ]

    for entry in sample_data:
        birth_year = entry["dob"].year
        player = Player(
            full_name=entry["full_name"],
            dob=entry["dob"],
            birth_year=birth_year,
            jersey_number=entry["jersey_number"],
            parent_email=entry["parent_email"]
        )
        db.add(player)
        db.flush()  # ensures `player.id` is available

        for reg in entry["registrations"]:
            registration = Registration(
                player_id=player.id,
                sport=reg["sport"],
                season=reg["season"],
                created_at=datetime.utcnow()
            )
            db.add(registration)

    db.commit()
    db.close()
    print("✅ Sample data seeded.")

if __name__ == "__main__":
    seed_data()

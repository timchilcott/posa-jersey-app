from sqlalchemy.orm import Session
from datetime import datetime
from ..models import Player

JERSEY_POOL = list(range(1, 100))  # 1–99

def assign_jersey_number(db, division: str) -> int:
    from app.models import Registration  # local import to avoid circular issues

    # Get all registrations for this division
    regs = db.query(Registration).filter(Registration.division == division).all()
    
    # Get all jersey numbers already used by players in this division
    taken = {reg.player.jersey_number for reg in regs if reg.player and reg.player.jersey_number}

    # Find the lowest unused number
    for num in range(1, 100):
        if num not in taken:
            return num

    # Fallback if all are used
    return 99
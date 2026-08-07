from typing import Optional, Union


def assign_jersey_number(db, group: Optional[Union[int, str]] = None) -> int:
    """
    Assign the lowest available jersey number for a birth year or division.
    If no group is provided, just return 1.
    """
    # local import to avoid circular import
    from app.models import Player, Registration

    if group is None:
        return 1

    if isinstance(group, int):
        players = db.query(Player).filter(Player.birth_year == group).all()
    else:
        players = (
            db.query(Player)
            .join(Registration)
            .filter(Registration.division == str(group))
            .all()
        )

    # Get all jersey numbers already used by players in this birth year
    taken = {
        player.jersey_number
        for player in players
        if player.jersey_number
    }

    # Find the lowest unused number
    for num in range(1, 100):
        if num not in taken:
            return num

    # Fallback if all are used
    return 99

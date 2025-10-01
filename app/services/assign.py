def assign_jersey_number(db, birth_year: int | None = None) -> int:
    """
    Assign the lowest available jersey number for a given birth year.
    If no birth year provided, just return 1.
    """
    # local import to avoid circular import
    from app.models import Player

    if birth_year is None:
        return 1

    # Get all players with this birth year
    players = (
        db.query(Player)
        .filter(Player.birth_year == birth_year)
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

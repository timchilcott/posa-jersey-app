import argparse
import logging
from app.database import SessionLocal
from app.models import Player, Registration
from app.services.assign import assign_jersey_number
from app.email import normalize_division


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Add a player and registration manually")
    parser.add_argument("full_name")
    parser.add_argument("parent_email")
    parser.add_argument("sport")
    parser.add_argument("division")
    parser.add_argument("season")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        division = normalize_division(args.division)
        jersey = assign_jersey_number(db, division)
        player = Player(full_name=args.full_name, parent_email=args.parent_email, jersey_number=jersey)
        db.add(player)
        db.flush()
        reg = Registration(
            player_id=player.id,
            program=f"{args.season} {args.sport}",
            division=division,
            sport=args.sport.strip().lower(),
            season=args.season,
        )
        db.add(reg)
        db.commit()
        logger.info(
            "Added player %s (ID %s) with jersey #%s",
            player.full_name,
            player.id,
            jersey,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

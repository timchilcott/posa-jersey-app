import argparse
import logging
from app.database import SessionLocal
from app.models import Registration


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Replace empty division values with canonical names")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without committing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        regs = db.query(Registration).filter((Registration.division == "") | (Registration.division.is_(None))).all()
        updated = 0
        for reg in regs:
            prog = (reg.program or "").lower()
            if "high school" in prog:
                reg.division = "High School"
            else:
                reg.division = "Unknown"
            updated += 1
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
        logger.info("Updated %d registrations", updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()

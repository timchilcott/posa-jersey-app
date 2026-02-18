"""
Cleanup script: Merge duplicate players caused by nickname mismatches.

Finds players whose names differ only by a parenthetical nickname
(e.g. "Emeryn (emmy) Miskin" vs "Emeryn Miskin"), merges their
registrations onto the original record, and deletes the duplicate.

Usage:
    python cleanup_duplicates.py          # Dry run (shows what would happen)
    python cleanup_duplicates.py --apply  # Actually apply changes

Run this AFTER deploying the updated sportsengine.py to prevent
future duplicates.
"""

import re
import sys
import os

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import get_db, SessionLocal
from app.models import Player, Registration
from sqlalchemy import func


def strip_nickname(name: str) -> str:
    """Remove parenthetical nicknames: 'Emeryn (emmy) Miskin' -> 'Emeryn Miskin'"""
    stripped = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
    return " ".join(stripped.split())


def find_duplicate_groups(db):
    """
    Find groups of players where one name is the nickname variant of another.
    Returns list of (original, duplicate) tuples.
    """
    # Get all players whose names contain parentheses (likely nickname variants)
    nickname_players = db.query(Player).filter(
        Player.full_name.like('%(%')
    ).all()

    duplicates = []

    for dup in nickname_players:
        stripped = strip_nickname(dup.full_name)

        # Find the original (non-nickname) player with the stripped name
        original = db.query(Player).filter(
            func.lower(Player.full_name) == stripped.lower(),
            Player.id != dup.id
        ).first()

        if original:
            duplicates.append((original, dup))

    return duplicates


def merge_player(db, original, duplicate, apply=False):
    """
    Merge duplicate player into original:
    1. Move any unique registrations from duplicate to original
    2. Delete redundant registrations on duplicate
    3. Delete duplicate player
    """
    print(f"\n{'='*60}")
    print(f"  ORIGINAL:  [{original.id}] {original.full_name} (jersey #{original.jersey_number})")
    print(f"  DUPLICATE: [{duplicate.id}] {duplicate.full_name} (jersey #{duplicate.jersey_number})")
    print(f"{'='*60}")

    # Get registrations for both
    orig_regs = db.query(Registration).filter(
        Registration.player_id == original.id
    ).all()
    dup_regs = db.query(Registration).filter(
        Registration.player_id == duplicate.id
    ).all()

    print(f"\n  Original has {len(orig_regs)} registration(s):")
    for r in orig_regs:
        print(f"    - {r.sport} / {r.season} / {r.division} (confirmed={r.confirmation_sent})")

    print(f"\n  Duplicate has {len(dup_regs)} registration(s):")
    for r in dup_regs:
        print(f"    - {r.sport} / {r.season} / {r.division} (confirmed={r.confirmation_sent})")

    # Build a set of (sport, season) combos the original already has
    orig_keys = {
        (r.sport.lower() if r.sport else '', r.season.lower() if r.season else '')
        for r in orig_regs
    }

    moved = 0
    deleted = 0

    for dup_reg in dup_regs:
        key = (
            dup_reg.sport.lower() if dup_reg.sport else '',
            dup_reg.season.lower() if dup_reg.season else ''
        )

        if key not in orig_keys:
            # Original doesn't have this registration — move it over
            print(f"\n  MOVE: {dup_reg.sport}/{dup_reg.season} -> original player [{original.id}]")
            if apply:
                dup_reg.player_id = original.id
            moved += 1
        else:
            # Original already has this registration — delete the duplicate's copy
            print(f"  DELETE REG: {dup_reg.sport}/{dup_reg.season} (redundant)")
            if apply:
                db.delete(dup_reg)
            deleted += 1

    # Delete the duplicate player
    print(f"\n  DELETE PLAYER: [{duplicate.id}] {duplicate.full_name}")
    if apply:
        # Flush registration changes first
        db.flush()
        db.delete(duplicate)

    print(f"\n  Summary: {moved} reg(s) moved, {deleted} reg(s) deleted, 1 player deleted")
    return moved, deleted


def main():
    apply = "--apply" in sys.argv

    if apply:
        print("*** LIVE MODE — changes will be applied ***\n")
    else:
        print("*** DRY RUN — no changes will be made (use --apply to execute) ***\n")

    db = SessionLocal()

    try:
        duplicates = find_duplicate_groups(db)

        if not duplicates:
            print("No nickname duplicates found. Database is clean!")
            return

        print(f"Found {len(duplicates)} duplicate group(s):\n")

        total_moved = 0
        total_deleted = 0

        for original, duplicate in duplicates:
            moved, deleted = merge_player(db, original, duplicate, apply=apply)
            total_moved += moved
            total_deleted += deleted

        if apply:
            db.commit()
            print(f"\n{'='*60}")
            print(f"DONE. Merged {len(duplicates)} duplicate(s).")
            print(f"  {total_moved} registration(s) moved")
            print(f"  {total_deleted} registration(s) deleted")
            print(f"  {len(duplicates)} player(s) deleted")
        else:
            print(f"\n{'='*60}")
            print(f"DRY RUN COMPLETE. Would merge {len(duplicates)} duplicate(s).")
            print(f"Run with --apply to execute.")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

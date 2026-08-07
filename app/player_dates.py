from datetime import date, datetime
from typing import Optional


def parse_date_of_birth(value) -> Optional[date]:
    """Parse DOB values from forms, APIs, and existing date objects."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def birth_year_from_date_of_birth(value) -> Optional[int]:
    dob = parse_date_of_birth(value)
    return dob.year if dob else None


def age_group_for_season(value, season_start_year: int) -> Optional[int]:
    birth_year = birth_year_from_date_of_birth(value)
    if not birth_year or not season_start_year:
        return None
    return season_start_year - birth_year + 1


def date_of_birth_iso(value) -> Optional[str]:
    dob = parse_date_of_birth(value)
    return dob.isoformat() if dob else None

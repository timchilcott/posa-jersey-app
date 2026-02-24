"""
SportsEngine API Integration Service

Handles OAuth authentication, GraphQL queries, and syncing registrations
from SportsEngine to the local database.

TARGETED FIXES (Feb 2026):
- extract_sport_from_registration_name returns Title Case ("Soccer" not "soccer")
- extract_season_from_registration_name returns "Spring 2026" not just "2026"
- process_single_registration uses case-insensitive name matching
- process_single_registration uses year-fallback matching for seasons
- Added is_configured() helper for sync_routes.py

FIX (Feb 18, 2026):
- Nickname-aware player matching: "Emeryn (emmy) Miskin" matches "Emeryn Miskin"
- Parent/guardian detection: skip registrants with no DOB or adult DOB

FIX (Feb 19, 2026):
- Fixed GraphQL FilterOption.operator: `operator: EQUAL` (required field)
- Incremental sync: skip expensive detail queries for profiles already in DB
- Fixed process_webhook: always trigger sync on any incoming webhook POST
  (previous version filtered on resourceType/resourceOperation which didn't
  match SportsEngine's actual payload format)
"""

import os
import re
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Ensure messages actually appear in Render logs
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(_handler)

# ---------------------------------------------------------------------
# Configuration  (ORIGINAL URLs — do NOT change)
# ---------------------------------------------------------------------
SPORTSENGINE_AUTH_URL = "https://user.sportngin.com/oauth/token"
SPORTSENGINE_GRAPHQL_URL = "https://api.sportsengine.com/graphql"

# Cache for access token
_token_cache = {
    "access_token": None,
    "expires_at": None
}


def is_configured() -> bool:
    """Check if SportsEngine integration is configured with all required env vars."""
    client_id = os.getenv("SPORTSENGINE_CLIENT_ID")
    client_secret = os.getenv("SPORTSENGINE_CLIENT_SECRET")
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    return bool(client_id and client_secret and org_id)


# ---------------------------------------------------------------------
# OAuth Authentication
# ---------------------------------------------------------------------
def get_access_token() -> str:
    """
    Get a valid access token using client credentials flow.
    Caches the token until it expires.
    """
    global _token_cache
    
    # Check if we have a valid cached token
    if _token_cache["access_token"] and _token_cache["expires_at"]:
        if datetime.now() < _token_cache["expires_at"]:
            return _token_cache["access_token"]
    
    client_id = os.getenv("SPORTSENGINE_CLIENT_ID")
    client_secret = os.getenv("SPORTSENGINE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError("SPORTSENGINE_CLIENT_ID and SPORTSENGINE_CLIENT_SECRET must be set")
    
    response = requests.post(
        SPORTSENGINE_AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    if response.status_code != 200:
        logger.error(f"OAuth token request failed: {response.status_code} - {response.text}")
        raise Exception(f"Failed to get access token: {response.status_code}")
    
    data = response.json()
    _token_cache["access_token"] = data["access_token"]
    # Set expiry 5 minutes before actual expiry to be safe
    expires_in = data.get("expires_in", 3600) - 300
    _token_cache["expires_at"] = datetime.now() + timedelta(seconds=expires_in)
    
    logger.info("Successfully obtained SportsEngine access token")
    return _token_cache["access_token"]


# ---------------------------------------------------------------------
# GraphQL Queries  (ORIGINAL queries — do NOT change)
# ---------------------------------------------------------------------
def graphql_query(query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query against the SportsEngine API."""
    token = get_access_token()
    
    response = requests.post(
        SPORTSENGINE_GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    
    if response.status_code != 200:
        logger.error(f"GraphQL query failed: {response.status_code} - {response.text}")
        raise Exception(f"GraphQL query failed: {response.status_code}")
    
    result = response.json()
    
    if "errors" in result:
        logger.error(f"GraphQL errors: {result['errors']}")
        raise Exception(f"GraphQL errors: {result['errors']}")
    
    return result.get("data", {})


def get_all_registrations() -> list:
    """
    Get all registration forms/events from SportsEngine.
    Returns list of registration IDs and names.
    """
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    if not org_id:
        raise ValueError("SPORTSENGINE_ORG_ID must be set")
    
    query = """
    query GetOrganization($orgId: Int!) {
        organization(id: $orgId) {
            id
            name
            registrations(perPage: 100, page: 1) {
                pageInformation {
                    pages
                    count
                    page
                    perPage
                }
                results {
                    id
                    name
                    status
                }
            }
        }
    }
    """
    
    data = graphql_query(query, {"orgId": int(org_id)})
    org = data.get("organization", {})
    registrations = org.get("registrations", {}).get("results", [])
    
    logger.info(f"SYNC: Found {len(registrations)} registration forms")
    
    return [
        {
            "id": reg["id"],
            "name": reg["name"],
            "status": reg.get("status", "UNKNOWN"),
            "count": 0
        }
        for reg in registrations
    ]


def get_registration_results(registration_id: str, cursor: str = None, known_names: set = None) -> dict:
    """
    Get all registration results (athletes) for a specific registration form.
    Uses the profile-based query approach that matches this API's schema.
    
    known_names: optional set of lowercased player names already in our DB
    for this sport+season. Detail queries are skipped for these profiles
    (incremental sync optimisation).
    """
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    
    if known_names is None:
        known_names = set()
    
    page = 1 if not cursor else int(cursor)
    
    # First, get the registration name
    reg_name_query = """
    query GetRegistration($regId: ID!, $orgId: Int!) {
        registration(id: $regId, organizationId: $orgId) {
            id
            name
        }
    }
    """
    
    registration_name = "Unknown"
    try:
        reg_data = graphql_query(reg_name_query, {"regId": str(registration_id), "orgId": int(org_id)})
        registration_name = reg_data.get("registration", {}).get("name", "Unknown")
        print(f"SYNC: Registration name: {registration_name}", flush=True)
    except Exception as e:
        print(f"SYNC: Could not fetch registration name for {registration_id}: {e}", flush=True)
    
    # Get profiles who submitted this registration
    # FIX (Feb 19, 2026): operator: EQUAL — required field, correct enum value
    list_query = """
    query GetRegistrationProfiles($orgId: Int!, $regId: String!, $page: Int!) {
        profiles(
            organizationId: $orgId
            filter: {
                key: REGISTRATION_SUBMITTED
                operator: EQUAL
                value: "true"
                source: REGISTRATIONS
                sourceId: $regId
            }
            page: $page
            perPage: 50
        ) {
            pageInformation {
                pages
                count
                page
                perPage
            }
            results {
                id
                firstName
                lastName
                dateOfBirth
                email
            }
        }
    }
    """
    
    variables = {
        "orgId": int(org_id),
        "regId": str(registration_id),
        "page": page
    }
    
    print(f"SYNC: Querying profiles for registration {registration_id} (page {page})...", flush=True)
    try:
        data = graphql_query(list_query, variables)
    except Exception as e:
        print(f"SYNC: PROFILES QUERY FAILED: {e}", flush=True)
        raise
    
    profiles_data = data.get("profiles", {})
    page_info = profiles_data.get("pageInformation", {})
    profiles = profiles_data.get("results", [])
    print(f"SYNC: Found {len(profiles)} profiles for registration {registration_id} (page {page}, total pages: {page_info.get('pages', '?')})", flush=True)
    
    # For each profile, get their registration answers
    # OPTIMIZATION: skip detail query for profiles already in our DB
    results = []
    skipped_count = 0
    fetched_count = 0
    for i, profile in enumerate(profiles):
        profile_id = profile.get("id")
        first = (profile.get("firstName") or "").strip()
        last = (profile.get("lastName") or "").strip()
        full_name_lower = f"{first} {last}".strip().lower()
        
        # Also check without nicknames
        stripped_lower = re.sub(r'\s*\([^)]*\)\s*', ' ', full_name_lower)
        stripped_lower = " ".join(stripped_lower.split())
        
        # --- Incremental sync: skip profiles we already have ---
        if full_name_lower in known_names or stripped_lower in known_names:
            skipped_count += 1
            # Still return basic info so process_single_registration can
            # update existing records (e.g. division changes)
            results.append({
                "id": profile.get("id"),
                "registrant": {
                    "id": profile.get("id"),
                    "firstName": profile.get("firstName"),
                    "lastName": profile.get("lastName"),
                    "dateOfBirth": profile.get("dateOfBirth"),
                    "email": profile.get("email")
                },
                "answers": [],
                "createdAt": None,
                "updatedAt": None
            })
            continue
        
        fetched_count += 1
        
        # Rate limit protection
        if fetched_count > 1:
            import time
            time.sleep(1.5)
        
        detail_query = """
        query GetProfileDetails($profileId: Int!, $orgId: Int!) {
            profile(id: $profileId, organizationId: $orgId) {
                id
                firstName
                lastName
                dateOfBirth
                email
                registrationResults(perPage: 100) {
                    results {
                        id
                        registrationId
                        registrationName
                        created
                        updated
                        answers {
                            name
                            format
                            ...on StringRegistrationResultAnswer {
                                stringValue: value
                            }
                            ...on ArrayRegistrationResultAnswer {
                                arrayValue: value
                            }
                            ...on NumberRegistrationResultAnswer {
                                numberValue: value
                            }
                        }
                    }
                }
            }
        }
        """
        
        try:
            profile_data = graphql_query(detail_query, {
                "profileId": int(profile_id),
                "orgId": int(org_id)
            })
            
            full_profile = profile_data.get("profile", {})
            reg_results = full_profile.get("registrationResults", {}).get("results", [])
            
            # Find matching registration result
            matching_result = None
            for rr in reg_results:
                if str(rr.get("registrationId")) == str(registration_id):
                    matching_result = rr
                    break
            
            # Build answers list
            answers = []
            if matching_result:
                for ans in matching_result.get("answers", []):
                    value = ans.get("stringValue") or ans.get("arrayValue") or ans.get("numberValue") or ""
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    answers.append({
                        "question": {"label": ans.get("name", "")},
                        "value": str(value)
                    })
            
            results.append({
                "id": full_profile.get("id"),
                "registrant": {
                    "id": full_profile.get("id"),
                    "firstName": full_profile.get("firstName"),
                    "lastName": full_profile.get("lastName"),
                    "dateOfBirth": full_profile.get("dateOfBirth"),
                    "email": full_profile.get("email")
                },
                "answers": answers,
                "createdAt": matching_result.get("created") if matching_result else None,
                "updatedAt": matching_result.get("updated") if matching_result else None
            })
            
        except Exception as e:
            logger.warning(f"Failed to get details for profile {profile_id}: {e}")
            results.append({
                "id": profile.get("id"),
                "registrant": {
                    "id": profile.get("id"),
                    "firstName": profile.get("firstName"),
                    "lastName": profile.get("lastName"),
                    "dateOfBirth": profile.get("dateOfBirth"),
                    "email": profile.get("email")
                },
                "answers": [],
                "createdAt": None,
                "updatedAt": None
            })
    
    if skipped_count > 0:
        print(f"SYNC: Skipped {skipped_count} existing profiles, fetched details for {fetched_count} new profiles", flush=True)
    
    has_next = page < page_info.get("pages", 1)
    return {
        "registrationForm": {
            "id": registration_id,
            "name": registration_name,
            "registrations": {
                "pageInfo": {
                    "hasNextPage": has_next,
                    "endCursor": str(page + 1) if has_next else None
                },
                "nodes": results
            }
        }
    }


# ---------------------------------------------------------------------
# Data Extraction Helpers
# ---------------------------------------------------------------------
def extract_sport_from_registration_name(registration_name: str) -> str:
    """
    Extract sport from registration form name.
    Returns Title Case to match the rest of the app (UI, email templates, etc.).

    Examples:
        "2025 Spring Soccer"              -> "Soccer"
        "Fall 2025 Basketball Registration" -> "Basketball"
        "Pines Volleyball 2025"           -> "Volleyball"
        "2026 Flag Football"              -> "Flag Football"
    """
    name_lower = registration_name.lower()

    # Order matters: check multi-word sports first
    sports = [
        ("flag football", "Flag Football"),
        ("flag", "Flag Football"),
        ("soccer", "Soccer"),
        ("basketball", "Basketball"),
        ("baseball", "Baseball"),
        ("softball", "Softball"),
        ("volleyball", "Volleyball"),
    ]

    for keyword, title_case in sports:
        if keyword in name_lower:
            return title_case

    logger.warning(f"Could not extract sport from registration name: {registration_name}")
    return "Unknown"


def extract_season_from_registration_name(registration_name: str) -> str:
    """
    Extract season from registration form name.
    Returns "Season Year" format (e.g. "Spring 2026") to match existing data.

    Examples:
        "2025 Spring Soccer"       -> "Spring 2025"
        "Fall 2025 Basketball"     -> "Fall 2025"
        "Pines Volleyball 2025"    -> "2025" (no season keyword found)
        "2026 Spring Soccer Reg"   -> "Spring 2026"
    """
    name_lower = registration_name.lower()

    # Find the year
    year_match = re.search(r'(20\d{2})', registration_name)
    year = year_match.group(1) if year_match else str(datetime.now().year)

    # Find season keyword
    for keyword in ["spring", "fall", "winter", "summer"]:
        if keyword in name_lower:
            return f"{keyword.capitalize()} {year}"

    # No season keyword — return just the year
    return year


def extract_division(answers: list) -> str:
    """
    Extract division from registration answers.
    """
    if not answers:
        return "Waiting Room"
    
    for answer in answers:
        question = answer.get("question", {})
        label = (question.get("label") or "").strip().lower()
        value = (answer.get("value") or "").strip()
        
        if label in ["division", "age division", "player division", "age group"]:
            if value:
                value_upper = value.upper()
                if value_upper in ["U3", "U4", "U5", "U6", "U8", "U10", "U12", "U14"]:
                    return value_upper
                if "high school" in value.lower() or "hs" in value.lower():
                    return "Pend Oreille Pines (High School Club Team)"
                return value
    
    logger.info("No Division field found in registration answers, placing in Waiting Room")
    return "Waiting Room"


def extract_grade(answers: list) -> Optional[str]:
    """Extract grade from registration answers."""
    if not answers:
        return None

    for answer in answers:
        question = answer.get("question", {})
        label = (question.get("label") or "").strip().lower()
        value = (answer.get("value") or "").strip()

        if label in ["grade", "school grade", "current grade", "grade level"]:
            if value:
                return value

    return None


def extract_birth_year(registrant: dict) -> Optional[int]:
    """Extract birth year from registrant's date of birth."""
    dob = registrant.get("dateOfBirth")
    if not dob:
        return None
    
    try:
        if isinstance(dob, str):
            if "-" in dob:
                return int(dob.split("-")[0])
            if "/" in dob:
                parts = dob.split("/")
                if len(parts) == 3:
                    year = parts[2]
                    if len(year) == 4:
                        return int(year)
        return None
    except (ValueError, IndexError) as e:
        logger.warning(f"Could not parse birth date: {dob} - {e}")
        return None


def extract_parent_email(registration: dict) -> str:
    """Extract parent/guardian email from registration."""
    guardian = registration.get("guardian", {})
    if guardian and guardian.get("email"):
        return guardian["email"].lower().strip()
    
    registrant = registration.get("registrant", {})
    if registrant and registrant.get("email"):
        return registrant["email"].lower().strip()
    
    return "unknown@example.com"


def extract_player_name(registrant: dict) -> str:
    """Extract full name from registrant."""
    first = (registrant.get("firstName") or "").strip()
    last = (registrant.get("lastName") or "").strip()
    return f"{first} {last}".strip() or "Unknown Player"


# ---------------------------------------------------------------------
# Name normalization helpers  (NEW — Feb 18, 2026)
# ---------------------------------------------------------------------

# Common first-name variants: maps short/nickname forms to canonical names
# and vice versa.  Used by _find_existing_player to match "Sam" ↔ "Samuel".
_NAME_VARIANTS = {
    "sam": ["samuel", "samantha"],
    "samuel": ["sam"],
    "samantha": ["sam"],
    "mike": ["michael"],
    "michael": ["mike"],
    "matt": ["matthew"],
    "matthew": ["matt"],
    "will": ["william"],
    "william": ["will", "bill", "billy"],
    "bill": ["william"],
    "billy": ["william"],
    "bob": ["robert"],
    "robert": ["bob", "rob", "bobby", "robbie"],
    "rob": ["robert"],
    "bobby": ["robert"],
    "robbie": ["robert"],
    "jim": ["james"],
    "jimmy": ["james"],
    "james": ["jim", "jimmy"],
    "joe": ["joseph"],
    "joseph": ["joe", "joey"],
    "joey": ["joseph"],
    "tom": ["thomas"],
    "thomas": ["tom", "tommy"],
    "tommy": ["thomas"],
    "dan": ["daniel"],
    "danny": ["daniel"],
    "daniel": ["dan", "danny"],
    "dave": ["david"],
    "david": ["dave"],
    "steve": ["steven", "stephen"],
    "steven": ["steve"],
    "stephen": ["steve"],
    "chris": ["christopher", "christian", "christina", "christine"],
    "christopher": ["chris"],
    "christian": ["chris"],
    "christina": ["chris", "tina"],
    "christine": ["chris"],
    "tina": ["christina"],
    "nick": ["nicholas", "nicolas"],
    "nicholas": ["nick"],
    "nicolas": ["nick"],
    "tony": ["anthony"],
    "anthony": ["tony"],
    "ben": ["benjamin"],
    "benjamin": ["ben"],
    "alex": ["alexander", "alexandra", "alexis"],
    "alexander": ["alex"],
    "alexandra": ["alex"],
    "alexis": ["alex"],
    "jake": ["jacob"],
    "jacob": ["jake"],
    "josh": ["joshua"],
    "joshua": ["josh"],
    "nate": ["nathan", "nathaniel"],
    "nathan": ["nate"],
    "nathaniel": ["nate"],
    "zach": ["zachary"],
    "zachary": ["zach", "zack"],
    "zack": ["zachary"],
    "ed": ["edward", "edwin"],
    "edward": ["ed", "eddie"],
    "eddie": ["edward"],
    "charlie": ["charles"],
    "charles": ["charlie", "chuck"],
    "chuck": ["charles"],
    "rick": ["richard"],
    "rich": ["richard"],
    "richard": ["rick", "rich", "dick"],
    "dick": ["richard"],
    "pat": ["patrick", "patricia"],
    "patrick": ["pat"],
    "patricia": ["pat", "patty", "tricia"],
    "patty": ["patricia"],
    "tricia": ["patricia"],
    "jon": ["jonathan"],
    "jonathan": ["jon"],
    "jack": ["john", "jackson"],
    "john": ["jack", "johnny"],
    "johnny": ["john"],
    "jackson": ["jack"],
    "kate": ["katherine", "kathryn", "kaitlyn"],
    "katie": ["katherine", "kathryn", "kaitlyn"],
    "katherine": ["kate", "katie", "kathy"],
    "kathryn": ["kate", "katie", "kathy"],
    "kathy": ["katherine", "kathryn"],
    "kaitlyn": ["kate", "katie"],
    "liz": ["elizabeth"],
    "beth": ["elizabeth"],
    "elizabeth": ["liz", "beth", "lizzy", "betsy"],
    "lizzy": ["elizabeth"],
    "betsy": ["elizabeth"],
    "meg": ["megan", "margaret"],
    "megan": ["meg"],
    "margaret": ["meg", "maggie", "peggy"],
    "maggie": ["margaret"],
    "peggy": ["margaret"],
    "jen": ["jennifer"],
    "jenny": ["jennifer"],
    "jennifer": ["jen", "jenny"],
    "jess": ["jessica"],
    "jessica": ["jess", "jessie"],
    "jessie": ["jessica"],
    "mandy": ["amanda"],
    "amanda": ["mandy"],
    "becky": ["rebecca"],
    "rebecca": ["becky"],
    "abby": ["abigail"],
    "abigail": ["abby"],
    "maddie": ["madeline", "madison"],
    "madeline": ["maddie"],
    "madison": ["maddie"],
    "andy": ["andrew"],
    "drew": ["andrew"],
    "andrew": ["andy", "drew"],
    "greg": ["gregory"],
    "gregory": ["greg"],
    "tim": ["timothy"],
    "timothy": ["tim"],
    "ted": ["theodore", "edward"],
    "theodore": ["ted", "teddy"],
    "teddy": ["theodore"],
    "max": ["maxwell", "maximilian"],
    "maxwell": ["max"],
    "maximilian": ["max"],
    "eli": ["elijah", "elias"],
    "elijah": ["eli"],
    "elias": ["eli"],
    "em": ["emily", "emma"],
    "emily": ["em"],
    "emma": ["em"],
    "izzy": ["isabella", "isaiah"],
    "isabella": ["izzy", "bella"],
    "bella": ["isabella"],
    "isaiah": ["izzy"],
    "gabe": ["gabriel"],
    "gabriel": ["gabe"],
    "abe": ["abraham"],
    "abraham": ["abe"],
    "vince": ["vincent"],
    "vincent": ["vince", "vinny"],
    "vinny": ["vincent"],
    "ray": ["raymond"],
    "raymond": ["ray"],
    "larry": ["lawrence"],
    "lawrence": ["larry"],
    "harry": ["harold", "harrison"],
    "harold": ["harry"],
    "harrison": ["harry"],
    "hank": ["henry"],
    "henry": ["hank"],
    "phil": ["philip", "phillip"],
    "philip": ["phil"],
    "phillip": ["phil"],
    "wes": ["wesley"],
    "wesley": ["wes"],
    "cody": ["dakota"],  # less common but seen in youth sports
    "ty": ["tyler", "tyson"],
    "tyler": ["ty"],
    "tyson": ["ty"],
    "kat": ["katrina", "katelyn"],
    "katrina": ["kat"],
    "katelyn": ["kat", "kate"],
}


def _get_name_variants(first_name: str) -> list:
    """Return a list of common variant first names for the given name."""
    return _NAME_VARIANTS.get(first_name.lower(), [])


def _strip_nickname(name: str) -> str:
    """
    Remove parenthetical nicknames from a name.

    'Emeryn (emmy) Miskin'  -> 'Emeryn Miskin'
    'Robert (Bob) Jones Jr' -> 'Robert Jones Jr'
    'Plain Name'            -> 'Plain Name'
    """
    stripped = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
    return " ".join(stripped.split())  # collapse whitespace


def _is_likely_adult(birth_year: Optional[int]) -> bool:
    """
    Return True if birth_year suggests an adult (parent), not a youth player.
    Youth players in POSA are roughly born 2008-2023.
    Anyone born before 2005 is almost certainly a parent.
    """
    if birth_year is None:
        return False  # can't tell — let other checks handle it
    return birth_year < 2005


# ---------------------------------------------------------------------
# Season matching helper  (handles format mismatches)
# ---------------------------------------------------------------------
def _find_existing_registration(db, player_id: int, sport: str, season: str):
    """
    Find an existing registration for a player+sport, handling season format
    mismatches (e.g. "2026" vs "Spring 2026").

    Returns the Registration object or None.
    """
    from app.models import Registration
    from sqlalchemy import func

    # Try exact match first (case-insensitive sport)
    existing = db.query(Registration).filter(
        Registration.player_id == player_id,
        func.lower(Registration.sport) == sport.lower(),
        Registration.season == season
    ).first()

    if existing:
        return existing

    # Fallback: match on just the year component
    year_match = re.search(r'(20\d{2})', season)
    if year_match:
        year_str = year_match.group(1)
        existing = db.query(Registration).filter(
            Registration.player_id == player_id,
            func.lower(Registration.sport) == sport.lower(),
            Registration.season.contains(year_str)
        ).first()
        if existing:
            logger.info(
                f"SYNC: Matched via year fallback: DB has '{existing.season}', "
                f"sync has '{season}' for player_id={player_id} sport={sport}"
            )
    return existing


# ---------------------------------------------------------------------
# Player matching helper  (NEW — Feb 18, 2026)
# ---------------------------------------------------------------------
def _find_existing_player(db, player_name: str):
    """
    Find an existing Player by name, with progressive fuzzy matching:
      1. Exact match
      2. Case-insensitive match
      3. Match after stripping parenthetical nicknames from BOTH sides

    Returns the Player object or None.
    """
    from app.models import Player
    from sqlalchemy import func

    # 1. Exact match
    player = db.query(Player).filter(Player.full_name == player_name).first()
    if player:
        return player

    # 2. Case-insensitive match
    normalized = " ".join(player_name.lower().split())
    player = db.query(Player).filter(
        func.lower(Player.full_name) == normalized
    ).first()
    if player:
        return player

    # 3. Strip nicknames from the incoming name and try matching
    stripped_incoming = _strip_nickname(player_name)
    if stripped_incoming != player_name:
        # Try exact match on stripped name
        player = db.query(Player).filter(Player.full_name == stripped_incoming).first()
        if player:
            logger.info(
                f"SYNC: Nickname match: incoming '{player_name}' matched "
                f"existing '{player.full_name}' via stripped form '{stripped_incoming}'"
            )
            return player

        # Try case-insensitive match on stripped name
        stripped_lower = " ".join(stripped_incoming.lower().split())
        player = db.query(Player).filter(
            func.lower(Player.full_name) == stripped_lower
        ).first()
        if player:
            logger.info(
                f"SYNC: Nickname match (ci): incoming '{player_name}' matched "
                f"existing '{player.full_name}'"
            )
            return player

    # 4. Strip nicknames from DB names and compare to incoming stripped name
    #    This handles the reverse case: DB has "Emeryn (emmy) Miskin",
    #    incoming is "Emeryn Miskin"
    stripped_lower = " ".join(stripped_incoming.lower().split())
    all_candidates = db.query(Player).filter(
        Player.full_name.ilike(f"%{stripped_incoming.split()[0]}%")
    ).all() if stripped_incoming.split() else []

    for candidate in all_candidates:
        candidate_stripped = _strip_nickname(candidate.full_name).lower()
        candidate_stripped = " ".join(candidate_stripped.split())
        if candidate_stripped == stripped_lower:
            logger.info(
                f"SYNC: Reverse nickname match: incoming '{player_name}' matched "
                f"DB player '{candidate.full_name}' (both strip to '{stripped_incoming}')"
            )
            return candidate

    # 5. Common name variant matching: "Sam Crabtree" ↔ "Samuel Crabtree"
    parts = stripped_incoming.split()
    if len(parts) >= 2:
        first_name = parts[0]
        last_parts = " ".join(parts[1:])
        variants = _get_name_variants(first_name)
        for variant in variants:
            variant_full = f"{variant.capitalize()} {last_parts}"
            # Try case-insensitive match
            variant_lower = variant_full.lower()
            player = db.query(Player).filter(
                func.lower(Player.full_name) == variant_lower
            ).first()
            if player:
                logger.info(
                    f"SYNC: Name variant match: incoming '{player_name}' matched "
                    f"existing '{player.full_name}' via variant '{variant_full}'"
                )
                return player

    return None


# ---------------------------------------------------------------------
# Helper: build set of known player names for a form (incremental sync)
# ---------------------------------------------------------------------
def _get_known_names_for_form(db, sport: str, season: str) -> set:
    """
    Return a set of lowercased player full_names that already have a
    registration for this sport+season.  Used to skip expensive
    per-profile detail API calls on subsequent syncs.
    """
    from app.models import Player, Registration
    from sqlalchemy import func

    year_match = re.search(r'(20\d{2})', season)
    year_str = year_match.group(1) if year_match else season

    rows = (
        db.query(func.lower(Player.full_name))
        .join(Registration, Registration.player_id == Player.id)
        .filter(
            func.lower(Registration.sport) == sport.lower(),
            Registration.season.contains(year_str)
        )
        .all()
    )
    return {r[0] for r in rows}


# ---------------------------------------------------------------------
# Sync Logic
# ---------------------------------------------------------------------
def sync_registration(registration_id: str, db: Session) -> dict:
    """
    Sync all results from a specific SportsEngine registration form.
    """
    from app.models import Player, Registration
    from app.services.assign import assign_jersey_number
    
    results = {
        "new_players": 0,
        "existing_players": 0,
        "new_registrations": 0,
        "updated_registrations": 0,
        "skipped_parents": 0,
        "errors": []
    }
    
    cursor = None
    registration_name = None
    known_names = None
    
    while True:
        data = get_registration_results(registration_id, cursor, known_names=known_names)
        form_data = data.get("registrationForm", {})
        
        if not registration_name:
            registration_name = form_data.get("name", "Unknown")
        
        registrations_data = form_data.get("registrations", {})
        nodes = registrations_data.get("nodes", [])
        page_info = registrations_data.get("pageInfo", {})
        
        # Extract sport (Title Case) and season ("Spring 2026") from form name
        sport = extract_sport_from_registration_name(registration_name)
        season = extract_season_from_registration_name(registration_name)
        
        # Build known-names set once for incremental skip logic
        if known_names is None:
            known_names = _get_known_names_for_form(db, sport, season)
            if known_names:
                print(f"SYNC: {len(known_names)} players already in DB for {sport}/{season}", flush=True)
        
        print(f"SYNC: Processing form '{registration_name}' -> sport='{sport}', season='{season}', {len(nodes)} registrants", flush=True)
        logger.info(f"SYNC: Processing form '{registration_name}' -> sport='{sport}', season='{season}', {len(nodes)} registrants")
        
        for reg in nodes:
            try:
                process_single_registration(reg, sport, season, registration_name, db, results)
            except Exception as e:
                logger.error(f"Error processing registration {reg.get('id')}: {e}", exc_info=True)
                results["errors"].append(str(e))
        
        if page_info.get("hasNextPage"):
            cursor = page_info.get("endCursor")
        else:
            break
    
    db.commit()
    logger.info(f"SYNC: Complete for '{registration_name}': {results}")
    return results


def process_single_registration(
    reg: dict,
    sport: str,
    season: str,
    program_name: str,
    db: Session,
    results: dict
) -> None:
    """
    Process a single registration from SportsEngine.

    Changes from original:
    - Sport stored in Title Case
    - Season stored as "Spring 2026" format
    - Nickname-aware player name matching via _find_existing_player
    - Year-fallback season matching via _find_existing_registration
    - Parent/guardian detection: skip adults (born before 2005) with no
      division or Unknown sport
    """
    from app.models import Player, Registration
    from app.services.assign import assign_jersey_number
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    
    registrant = reg.get("registrant", {})
    if not registrant:
        logger.warning(f"Registration {reg.get('id')} has no registrant, skipping")
        return
    
    # Extract data
    player_name = extract_player_name(registrant)
    birth_year = extract_birth_year(registrant)
    parent_email = extract_parent_email(reg)
    division = extract_division(reg.get("answers", []))
    grade = extract_grade(reg.get("answers", []))
    order_number = reg.get("orderNumber")
    
    # ------------------------------------------------------------------
    # FIX: Parent/guardian detection
    # Skip registrants who are clearly adults (not youth players).
    # An adult is someone born before 2005, OR someone with no DOB whose
    # division is Waiting Room and sport is Unknown — they're almost
    # certainly a parent who got pulled in as a profile.
    # ------------------------------------------------------------------
    if _is_likely_adult(birth_year):
        logger.info(
            f"SYNC: Skipping likely parent/adult: {player_name} "
            f"(birth_year={birth_year})"
        )
        results["skipped_parents"] = results.get("skipped_parents", 0) + 1
        return

    if (birth_year is None
            and division == "Waiting Room"
            and sport == "Unknown"):
        logger.info(
            f"SYNC: Skipping likely parent (no DOB, no division, unknown sport): "
            f"{player_name}"
        )
        results["skipped_parents"] = results.get("skipped_parents", 0) + 1
        return
    
    print(f"SYNC: Processing {player_name} for {sport}/{season}, division='{division}'", flush=True)
    logger.info(f"SYNC: Processing {player_name} for {sport}/{season}, division='{division}'")
    
    # Parse created_at for order_date
    order_date = None
    created_at = reg.get("createdAt")
    if created_at:
        try:
            order_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except:
            pass
    
    # ---- Player matching: nickname-aware ----
    existing_player = _find_existing_player(db, player_name)
    
    if existing_player:
        # EXISTING PLAYER
        results["existing_players"] += 1
        player = existing_player
        
        if birth_year and not player.birth_year:
            player.birth_year = birth_year
        
        if parent_email != "unknown@example.com" and player.parent_email == "unknown@example.com":
            player.parent_email = parent_email
        
        if grade and hasattr(player, 'grade'):
            player.grade = grade
        
        # ---- Registration matching: year-fallback ----
        existing_reg = _find_existing_registration(db, player.id, sport, season)
        
        if existing_reg:
            if division != "Waiting Room" and existing_reg.division != division:
                logger.info(f"SYNC: Updating division for {player.full_name} ({sport}): '{existing_reg.division}' -> '{division}'")
                existing_reg.division = division
            existing_reg.order_number = order_number
            existing_reg.order_date = order_date
            results["updated_registrations"] += 1
            logger.info(f"SYNC: Updated registration for existing player: {player_name}")
        else:
            try:
                # If this player has ever been sent a confirmation,
                # they already have a jersey — auto-confirm the new season.
                # Otherwise leave False so they appear in "needs email".
                ever_confirmed = any(
                    r.confirmation_sent
                    for r in db.query(Registration).filter(
                        Registration.player_id == player.id
                    ).all()
                )
                new_reg = Registration(
                    player_id=player.id,
                    program=program_name,
                    division=division,
                    sport=sport,
                    season=season,
                    order_number=order_number,
                    order_date=order_date,
                    confirmation_sent=ever_confirmed
                )
                db.add(new_reg)
                db.flush()
                results["new_registrations"] += 1
                logger.info(f"SYNC: Added new {sport} registration for existing player: {player_name}")
            except IntegrityError:
                db.rollback()
                logger.info(f"SYNC: Registration already existed for {player_name} ({sport}/{season})")
                existing_reg = _find_existing_registration(db, player.id, sport, season)
                if existing_reg and division != "Waiting Room":
                    existing_reg.division = division
                    results["updated_registrations"] += 1
    
    else:
        # NEW PLAYER
        results["new_players"] += 1
        
        # Use the stripped (no-nickname) version as the canonical name
        normalized_player_name = _strip_nickname(player_name)
        normalized_player_name = " ".join(
            word.capitalize() for word in normalized_player_name.split()
        )
        
        jersey_number = None
        if birth_year:
            jersey_number = assign_jersey_number(db, birth_year)
        
        final_division = division
        if not birth_year or not jersey_number:
            final_division = "Waiting Room"
            logger.info(f"SYNC: Missing data for {normalized_player_name} (birth_year={birth_year}) - placing in Waiting Room")
        
        print(f"SYNC: Creating NEW player: {normalized_player_name} (email: {parent_email})", flush=True)
        logger.info(f"SYNC: Creating NEW player: {normalized_player_name} (email: {parent_email})")
        
        player_kwargs = dict(
            full_name=normalized_player_name,
            birth_year=birth_year,
            jersey_number=jersey_number,
            parent_email=parent_email
        )
        try:
            player = Player(**player_kwargs, grade=grade)
        except TypeError:
            player = Player(**player_kwargs)
        
        db.add(player)
        db.flush()
        
        new_reg = Registration(
            player_id=player.id,
            program=program_name,
            division=final_division,
            sport=sport,
            season=season,
            order_number=order_number,
            order_date=order_date,
            confirmation_sent=False
        )
        db.add(new_reg)
        results["new_registrations"] += 1
        
        logger.info(f"SYNC: Created new player: {normalized_player_name} (jersey #{jersey_number}, division: {final_division}, sport: {sport})")


def sync_all_registrations(db: Session) -> dict:
    """Sync all active registration forms from SportsEngine."""
    all_results = {
        "forms_processed": 0,
        "new_players": 0,
        "existing_players": 0,
        "new_registrations": 0,
        "updated_registrations": 0,
        "skipped_parents": 0,
        "errors": []
    }
    
    forms = get_all_registrations()
    print(f"SYNC: Found {len(forms)} total forms", flush=True)
    for f in forms:
        print(f"SYNC: Form '{f.get('name')}' status={repr(f.get('status'))}", flush=True)
    logger.info(f"SYNC: Found {len(forms)} total forms")
    
    processed_any = False
    
    for form in forms:
        status = form.get("status")
        # API may return numeric (1=active) or string ("ACTIVE"/"OPEN"/"CLOSED")
        is_active = (
            status in ["ACTIVE", "OPEN", "CLOSED"]
            or status in [1, "1", True]
        )
        if is_active:
            processed_any = True
            logger.info(f"SYNC: Syncing form '{form['name']}' (status={repr(status)}, count={form.get('count', '?')})")
            try:
                result = sync_registration(form["id"], db)
                all_results["forms_processed"] += 1
                all_results["new_players"] += result["new_players"]
                all_results["existing_players"] += result["existing_players"]
                all_results["new_registrations"] += result["new_registrations"]
                all_results["updated_registrations"] += result["updated_registrations"]
                all_results["skipped_parents"] += result.get("skipped_parents", 0)
                all_results["errors"].extend(result["errors"])
            except Exception as e:
                print(f"SYNC ERROR: Form '{form['name']}': {e}", flush=True)
                logger.error(f"Error syncing form {form['id']}: {e}", exc_info=True)
                all_results["errors"].append(f"Form {form['name']}: {str(e)}")
        else:
            print(f"SYNC: Skipping form '{form['name']}' (status={repr(status)})", flush=True)
            logger.info(f"SYNC: Skipping form '{form['name']}' (status={repr(status)})")
    
    # Fallback: if no forms matched the status filter, sync ALL forms
    if not processed_any and forms:
        print(f"SYNC: No forms matched status filter! Processing ALL {len(forms)} forms as fallback.", flush=True)
        logger.warning(f"SYNC: No forms matched status filter! Processing ALL {len(forms)} forms as fallback.")
        for form in forms:
            try:
                result = sync_registration(form["id"], db)
                all_results["forms_processed"] += 1
                all_results["new_players"] += result["new_players"]
                all_results["existing_players"] += result["existing_players"]
                all_results["new_registrations"] += result["new_registrations"]
                all_results["updated_registrations"] += result["updated_registrations"]
                all_results["skipped_parents"] += result.get("skipped_parents", 0)
                all_results["errors"].extend(result["errors"])
            except Exception as e:
                print(f"SYNC ERROR (fallback): Form '{form['name']}': {e}", flush=True)
                logger.error(f"Error syncing form {form['id']}: {e}", exc_info=True)
                all_results["errors"].append(f"Form {form['name']}: {str(e)}")
    
    print(f"SYNC: COMPLETE: {all_results}", flush=True)
    logger.info(f"SYNC: All forms complete: {all_results}")
    return all_results


def process_webhook(payload: dict, db: Session) -> dict:
    """
    Process a webhook notification from SportsEngine.

    Always triggers a full sync on any incoming webhook POST, regardless
    of payload structure.  SportsEngine's actual payload format varies
    and filtering on specific field names (resourceType, resourceOperation)
    caused missed syncs.  A full sync is cheap thanks to the incremental
    known_names optimization.
    """
    # Log whatever we got for debugging
    resource_type = payload.get("resourceType") or payload.get("type") or "unknown"
    operation = payload.get("resourceOperation") or payload.get("operation") or payload.get("action") or "unknown"
    resource_id = payload.get("resourceId") or payload.get("id") or "unknown"

    logger.info(f"WEBHOOK: Received — operation={operation} type={resource_type} id={resource_id}")
    logger.info(f"WEBHOOK: Full payload: {payload}")

    # Always sync both registrations and events
    results = {"registration_sync": None, "event_sync": None}

    try:
        reg_results = sync_all_registrations(db)
        results["registration_sync"] = {"action": "synced", "results": reg_results}
    except Exception as e:
        logger.error(f"WEBHOOK: Registration sync failed: {e}", exc_info=True)
        results["registration_sync"] = {"action": "error", "message": str(e)}

    try:
        event_results = sync_all_events(db)
        results["event_sync"] = {"action": "synced", "results": event_results}
    except Exception as e:
        logger.error(f"WEBHOOK: Event sync failed: {e}", exc_info=True)
        results["event_sync"] = {"action": "error", "message": str(e)}

    return results


# ---------------------------------------------------------------------
# Events API
# ---------------------------------------------------------------------

EVENTS_QUERY = """
query GetEvents($orgId: Int!, $page: Int!, $perPage: Int!) {
    events(
        organizationId: $orgId
        page: $page
        perPage: $perPage
    ) {
        pageInformation {
            pages
            count
            page
            perPage
        }
        results {
            id
            organizationId
            name
            type
            start
            end
            status
            description
            created
            updated
            location {
                name
                description
                url
                address
            }
            eventTeams {
                score
                primaryColor
                homeTeam
                name
            }
        }
    }
}
"""


TEAMS_LOGO_QUERY = """
query GetTeams($orgId: Int!, $page: Int!, $perPage: Int!) {
    teams(
        organizationId: $orgId
        page: $page
        perPage: $perPage
    ) {
        pageInformation {
            pages
            count
            page
            perPage
        }
        results {
            id
            name
            brand {
                logoUrl
            }
        }
    }
}
"""


def get_team_logo_map() -> dict:
    """
    Fetch all teams for the org and return a dict mapping
    lowercased team name -> logoUrl.  Only includes teams
    that actually have a logo.
    """
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    if not org_id:
        return {}

    logo_map = {}
    page = 1

    while True:
        try:
            data = graphql_query(TEAMS_LOGO_QUERY, {
                "orgId": int(org_id),
                "page": page,
                "perPage": 100,
            })
        except Exception as e:
            logger.warning(f"TEAMS LOGO: Failed to fetch page {page}: {e}")
            break

        teams_data = data.get("teams", {})
        page_info = teams_data.get("pageInformation", {})
        results = teams_data.get("results", [])

        for team in results:
            brand = team.get("brand") or {}
            logo_url = brand.get("logoUrl")
            name = team.get("name")
            if logo_url and name:
                logo_map[name.lower()] = logo_url

        if page >= page_info.get("pages", 1):
            break
        page += 1

    logger.info(f"TEAMS LOGO: Found {len(logo_map)} teams with logos")
    return logo_map


def get_events(page: int = 1, per_page: int = 100) -> dict:
    """
    Fetch events from SportsEngine for the configured organization.
    Date filtering is done in Python after fetching since the GraphQL
    schema does not support start/end arguments on the events query.
    """
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    if not org_id:
        raise ValueError("SPORTSENGINE_ORG_ID must be set")

    variables = {
        "orgId": int(org_id),
        "page": page,
        "perPage": min(per_page, 100),
    }

    data = graphql_query(EVENTS_QUERY, variables)
    return data.get("events", {})


def _extract_sport_from_event(event: dict) -> Optional[str]:
    """
    Try to determine the sport from event name or team names.
    Uses the same keyword matching as registration names but suppresses
    warnings since event/team names are often just people's names.
    """
    name_lower = (event.get("name") or "").lower()

    sports = [
        ("flag football", "Flag Football"),
        ("flag", "Flag Football"),
        ("soccer", "Soccer"),
        ("basketball", "Basketball"),
        ("baseball", "Baseball"),
        ("softball", "Softball"),
        ("volleyball", "Volleyball"),
    ]

    for keyword, title_case in sports:
        if keyword in name_lower:
            return title_case

    # Check team names (without logging warnings)
    for team in (event.get("eventTeams") or []):
        team_lower = (team.get("name") or "").lower()
        for keyword, title_case in sports:
            if keyword in team_lower:
                return title_case

    return None


def _parse_utc_datetime(dt_str: str) -> Optional[datetime]:
    """Parse a UTC datetime string from SportsEngine."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            logger.warning(f"Could not parse datetime: {dt_str}")
            return None


def sync_all_events(db: Session, days_back: int = 30, days_forward: int = 90) -> dict:
    """
    Sync events from SportsEngine.
    Fetches all pages of events, then filters to the date window
    [now - days_back, now + days_forward] before upserting.
    """
    from app.models_events import Event

    results = {
        "new_events": 0,
        "updated_events": 0,
        "total_fetched": 0,
        "skipped_out_of_range": 0,
        "errors": [],
    }

    now = datetime.utcnow()
    window_start = now - timedelta(days=days_back)
    window_end = now + timedelta(days=days_forward)

    logger.info(f"EVENT SYNC: Fetching events (date window {window_start.date()} to {window_end.date()})")

    # Fetch team logos once up-front so we can attach them to event teams
    logo_map = {}
    try:
        logo_map = get_team_logo_map()
    except Exception as e:
        logger.warning(f"EVENT SYNC: Could not fetch team logos: {e}")

    page = 1
    while True:
        try:
            events_data = get_events(page=page, per_page=100)
        except Exception as e:
            logger.error(f"EVENT SYNC: Failed to fetch page {page}: {e}")
            results["errors"].append(str(e))
            break

        page_info = events_data.get("pageInformation", {})
        events_list = events_data.get("results", [])

        logger.info(
            f"EVENT SYNC: Page {page}/{page_info.get('pages', '?')}, "
            f"{len(events_list)} events"
        )

        for event_data in events_list:
            try:
                # Filter by date window in Python
                event_start = _parse_utc_datetime(event_data.get("start"))
                if event_start and (event_start < window_start or event_start > window_end):
                    results["skipped_out_of_range"] += 1
                    continue
                _upsert_event(event_data, db, results, logo_map=logo_map)
            except Exception as e:
                logger.error(f"EVENT SYNC: Error processing event {event_data.get('id')}: {e}")
                results["errors"].append(str(e))

        results["total_fetched"] += len(events_list)

        if page >= page_info.get("pages", 1):
            break
        page += 1

    db.commit()
    logger.info(f"EVENT SYNC: Complete — {results}")
    return results


def _upsert_event(event_data: dict, db: Session, results: dict, logo_map: dict = None) -> None:
    """Create or update a single event from SportsEngine data."""
    from app.models_events import Event

    se_id = str(event_data.get("id"))
    if not se_id:
        return

    if logo_map is None:
        logo_map = {}

    # Extract location
    location = event_data.get("location") or {}
    address_data = location.get("address")
    if isinstance(address_data, dict):
        address_str = ", ".join(
            filter(None, [
                address_data.get("street"),
                address_data.get("city"),
                address_data.get("state"),
                address_data.get("zip"),
            ])
        )
    else:
        address_str = str(address_data) if address_data else None

    # Extract teams and match logos from the pre-fetched logo_map
    teams_raw = event_data.get("eventTeams") or []
    teams_json = []
    for t in teams_raw:
        team_entry = {
            "name": t.get("name"),
            "score": t.get("score"),
            "primaryColor": t.get("primaryColor"),
            "homeTeam": t.get("homeTeam"),
        }
        # Match logo by team name (case-insensitive)
        team_name = t.get("name") or ""
        logo_url = logo_map.get(team_name.lower())
        if logo_url:
            team_entry["logoUrl"] = logo_url
        teams_json.append(team_entry)

    sport = _extract_sport_from_event(event_data)
    start_time = _parse_utc_datetime(event_data.get("start"))
    end_time = _parse_utc_datetime(event_data.get("end"))
    se_created = _parse_utc_datetime(event_data.get("created"))
    se_updated = _parse_utc_datetime(event_data.get("updated"))

    existing = db.query(Event).filter(Event.se_event_id == se_id).first()

    if existing:
        existing.name = event_data.get("name", existing.name)
        existing.event_type = (event_data.get("type") or "event").lower()
        existing.sport = sport or existing.sport
        existing.start_time = start_time
        existing.end_time = end_time
        existing.status = event_data.get("status")
        existing.description = event_data.get("description")
        existing.location_name = location.get("name")
        existing.location_address = address_str
        existing.location_url = location.get("url")
        existing.location_description = location.get("description")
        existing.teams = teams_json if teams_json else existing.teams
        existing.se_updated_at = se_updated
        results["updated_events"] += 1
    else:
        new_event = Event(
            se_event_id=se_id,
            organization_id=str(event_data.get("organizationId", "")),
            name=event_data.get("name", "Untitled Event"),
            event_type=(event_data.get("type") or "event").lower(),
            sport=sport,
            start_time=start_time,
            end_time=end_time,
            status=event_data.get("status"),
            description=event_data.get("description"),
            location_name=location.get("name"),
            location_address=address_str,
            location_url=location.get("url"),
            location_description=location.get("description"),
            teams=teams_json if teams_json else None,
            se_created_at=se_created,
            se_updated_at=se_updated,
        )
        db.add(new_event)
        results["new_events"] += 1

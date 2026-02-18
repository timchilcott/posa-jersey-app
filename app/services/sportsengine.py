"""
SportsEngine API Integration Service

Handles OAuth authentication, GraphQL queries, and syncing registrations
from SportsEngine to the local database.

FIXES APPLIED:
- extract_sport_from_registration_name returns Title Case (matching UI)
- extract_season_from_registration_name returns "Spring 2026" not just "2026"
- process_single_registration uses year-fallback matching for seasons
- Sport stored in Title Case consistently
"""

import os
import logging
import requests
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configuration
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
# GraphQL Queries
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
        logger.error(f"GraphQL query failed: {response.status_code} - {response.text[:500]}")
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
    
    return [
        {
            "id": reg["id"],
            "name": reg["name"],
            "status": reg.get("status", "UNKNOWN"),
            "count": 0
        }
        for reg in registrations
    ]


def get_registration_results(registration_id: str, cursor: str = None) -> dict:
    """
    Get all registration results (athletes) for a specific registration form.
    First get profile list, then query each for full details.
    """
    org_id = os.getenv("SPORTSENGINE_ORG_ID")
    
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
        logger.info(f"Fetching registration name for ID: {registration_id}")
        reg_data = graphql_query(reg_name_query, {"regId": str(registration_id), "orgId": int(org_id)})
        logger.info(f"Registration query response: {reg_data}")
        registration_name = reg_data.get("registration", {}).get("name", "Unknown")
        logger.info(f"Extracted registration name: {registration_name}")
    except Exception as e:
        logger.warning(f"Could not fetch registration name for {registration_id}: {e}")
    
    # Step 1: Get list of profiles who submitted this registration
    list_query = """
    query GetRegistrationProfiles($orgId: Int!, $regId: String!, $page: Int!) {
        profiles(
            organizationId: $orgId
            filter: {
                key: REGISTRATION_SUBMITTED
                value: "true"
                source: REGISTRATIONS
                sourceId: $regId
                operator: EQUAL
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
    
    data = graphql_query(list_query, variables)
    
    profiles_data = data.get("profiles", {})
    page_info = profiles_data.get("pageInformation", {})
    profiles = profiles_data.get("results", [])
    
    # Step 2: For each profile, get their registration answers
    results = []
    for i, profile in enumerate(profiles):
        profile_id = profile.get("id")
        
        # Add delay between API calls to avoid rate limiting
        if i > 0:
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
        "Pines Volleyball 2025"    -> "2025" (no season keyword)
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
# Season matching helper
# ---------------------------------------------------------------------
def _find_existing_registration(db, player_id: int, sport: str, season: str):
    """
    Find an existing registration for a player+sport, handling season format
    mismatches (e.g. "2026" vs "Spring 2026").

    Returns the Registration object or None.
    """
    from app.models import Registration
    from sqlalchemy import func

    # Try exact match first
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
        "errors": []
    }
    
    cursor = None
    registration_name = None
    
    while True:
        data = get_registration_results(registration_id, cursor)
        form_data = data.get("registrationForm", {})
        
        if not registration_name:
            registration_name = form_data.get("name", "Unknown")
        
        registrations_data = form_data.get("registrations", {})
        nodes = registrations_data.get("nodes", [])
        page_info = registrations_data.get("pageInfo", {})
        
        # Extract sport (Title Case) and season ("Spring 2026") from form name
        sport = extract_sport_from_registration_name(registration_name)
        season = extract_season_from_registration_name(registration_name)

        logger.info(f"SYNC: Processing form '{registration_name}' -> sport='{sport}', season='{season}'")
        
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
    logger.info(f"Sync complete for {registration_name}: {results}")
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
    
    - Sport is stored in Title Case (e.g. "Soccer", "Basketball")
    - Season is stored as "Spring 2026", "Fall 2025", etc.
    - Matching uses year-fallback to handle format mismatches
    """
    from app.models import Player, Registration
    from app.services.assign import assign_jersey_number
    
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
    
    logger.info(f"SYNC: Processing {player_name} for {sport}/{season}")
    logger.info(f"SYNC: Division extracted: '{division}', Grade: '{grade}'")
    
    # Parse created_at for order_date
    order_date = None
    created_at = reg.get("createdAt")
    if created_at:
        try:
            order_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except:
            pass
    
    # Normalize player name for matching
    normalized_name = " ".join(player_name.lower().split())
    
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    
    # Check if player already exists — NAME matching ONLY
    existing_player = None
    match_method = None
    
    # Strategy 1: Exact name match
    existing_player = db.query(Player).filter(Player.full_name == player_name).first()
    if existing_player:
        match_method = "exact_name"
    
    # Strategy 2: Case-insensitive name match
    if not existing_player:
        existing_player = db.query(Player).filter(
            func.lower(Player.full_name) == normalized_name
        ).first()
        if existing_player:
            match_method = "case_insensitive_name"
    
    if existing_player:
        logger.info(f"SYNC: Found existing player via {match_method}: {existing_player.full_name} (ID: {existing_player.id})")
        results["existing_players"] += 1
        player = existing_player
        
        # Update birth year if we now have it and they don't
        if birth_year and not player.birth_year:
            player.birth_year = birth_year
        
        # Update parent email if we have a better one
        if parent_email != "unknown@example.com" and player.parent_email == "unknown@example.com":
            player.parent_email = parent_email
        
        # Update grade if we have it
        if grade:
            player.grade = grade
        
        # Check if they already have this sport+season (with year fallback)
        existing_reg = _find_existing_registration(db, player.id, sport, season)
        
        if existing_reg:
            # Registration exists — update division if needed
            if division != "Waiting Room" and existing_reg.division != division:
                logger.info(f"SYNC: Updating division for {player.full_name} ({sport}): '{existing_reg.division}' -> '{division}'")
                existing_reg.division = division
                results["updated_registrations"] += 1
            else:
                logger.info(f"SYNC: {player.full_name} ({sport}/{season}) already current")
        else:
            # New sport/season for this player
            try:
                new_reg = Registration(
                    player_id=player.id,
                    program=program_name,
                    division=division,
                    sport=sport,          # Title Case
                    season=season,        # "Spring 2026" format
                    order_number=order_number,
                    order_date=order_date,
                    confirmation_sent=True
                )
                db.add(new_reg)
                db.flush()
                logger.info(f"SYNC: Added {sport} for existing player: {player.full_name} with division '{division}'")
                results["new_registrations"] += 1
            except IntegrityError:
                db.rollback()
                existing_reg = _find_existing_registration(db, player.id, sport, season)
                if existing_reg and division != "Waiting Room":
                    existing_reg.division = division
                    results["updated_registrations"] += 1
                logger.info(f"SYNC: Registration already existed for {player.full_name} ({sport}), updated")
    
    else:
        # NEW PLAYER
        results["new_players"] += 1
        
        normalized_player_name = " ".join(word.capitalize() for word in player_name.split())
        
        jersey_number = None
        if birth_year:
            jersey_number = assign_jersey_number(db, birth_year)
        
        final_division = division
        if not birth_year or not jersey_number:
            final_division = "Waiting Room"
            logger.info(f"SYNC: Missing data for {normalized_player_name} (birth_year={birth_year}, jersey={jersey_number}) - placing in Waiting Room")
        
        logger.info(f"SYNC: Creating NEW player: {normalized_player_name} (email: {parent_email})")
        
        player = Player(
            full_name=normalized_player_name,
            birth_year=birth_year,
            grade=grade,
            jersey_number=jersey_number,
            parent_email=parent_email
        )
        db.add(player)
        db.flush()
        
        new_reg = Registration(
            player_id=player.id,
            program=program_name,
            division=final_division,
            sport=sport,          # Title Case
            season=season,        # "Spring 2026" format
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
        "errors": []
    }
    
    forms = get_all_registrations()
    
    for form in forms:
        if form.get("status") in ["ACTIVE", "OPEN", "CLOSED"]:
            try:
                result = sync_registration(form["id"], db)
                all_results["forms_processed"] += 1
                all_results["new_players"] += result["new_players"]
                all_results["existing_players"] += result["existing_players"]
                all_results["new_registrations"] += result["new_registrations"]
                all_results["updated_registrations"] += result["updated_registrations"]
                all_results["errors"].extend(result["errors"])
            except Exception as e:
                logger.error(f"Error syncing form {form['id']}: {e}")
                all_results["errors"].append(f"Form {form['name']}: {str(e)}")
    
    return all_results


def process_webhook(payload: dict, db: Session) -> dict:
    """
    Process a webhook notification from SportsEngine.
    """
    resource_type = payload.get("resourceType")
    operation = payload.get("resourceOperation")
    resource_id = payload.get("resourceId")
    webhook_org_id = payload.get("organizationId")
    
    logger.info(f"Webhook received: {operation} {resource_type} (id: {resource_id}, org: {webhook_org_id})")
    
    if resource_type != "registrationResult":
        return {"action": "ignored", "reason": f"Not registrationResult: {resource_type}"}
    
    if operation not in ["create", "update"]:
        return {"action": "ignored", "reason": f"Not create/update: {operation}"}
    
    try:
        from app.models import Player, Registration
        from app.services.assign import assign_jersey_number
        
        env_org_id = os.getenv("SPORTSENGINE_ORG_ID")
        
        registrations = get_all_registrations()
        active_regs = [r for r in registrations if r.get("status") == 1]
        
        if not active_regs:
            return {"action": "ignored", "reason": "No active registrations"}
        
        processed = []
        
        for reg in active_regs:
            reg_id = reg["id"]
            reg_name = reg["name"]
            
            query = """
            query GetRecentProfiles($orgId: Int!, $regId: String!) {
                profiles(
                    organizationId: $orgId
                    filter: {
                        key: registration_submitted
                        value: "true"
                        source: registration
                        sourceId: $regId
                        operator: equal
                    }
                    perPage: 10
                ) {
                    results {
                        id
                        firstName
                        lastName
                        dateOfBirth
                        email
                        registrationResults(perPage: 5) {
                            results {
                                id
                                registrationId
                                registrationName
                                created
                                answers {
                                    name
                                    format
                                    ...on StringRegistrationResultAnswer {
                                        stringValue: value
                                    }
                                    ...on ArrayRegistrationResultAnswer {
                                        arrayValue: value
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
            
            data = graphql_query(query, {
                "orgId": int(env_org_id),
                "regId": str(reg_id)
            })
            
            profiles = data.get("profiles", {}).get("results", [])
            
            for profile in profiles:
                reg_results = profile.get("registrationResults", {}).get("results", [])
                
                for rr in reg_results:
                    if str(rr.get("registrationId")) != str(reg_id):
                        continue
                    
                    created = rr.get("created")
                    if created:
                        from datetime import timezone
                        try:
                            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            now = datetime.now(timezone.utc)
                            if now - created_dt > timedelta(minutes=10):
                                continue
                        except:
                            pass
                    
                    result = process_webhook_profile(profile, rr, reg_name, db)
                    if result:
                        processed.append(result)
                    break
        
        if processed:
            return {"action": "processed", "results": processed}
        else:
            return {"action": "no_recent", "reason": "No recent registrations found"}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return {"action": "error", "message": str(e)}


def process_webhook_profile(profile: dict, reg_result: dict, reg_name: str, db: Session) -> dict:
    """
    Process a single profile from a webhook.
    Uses the same matching logic as sync to avoid duplicates.
    """
    from app.models import Player, Registration
    from app.services.assign import assign_jersey_number
    from sqlalchemy import func
    
    player_name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    
    birth_year = None
    dob = profile.get("dateOfBirth")
    if dob and "-" in str(dob):
        try:
            birth_year = int(str(dob).split("-")[0])
        except:
            pass
    
    parent_email = (profile.get("email") or "unknown@example.com").lower().strip()
    
    # Extract division and grade from answers
    division = "Waiting Room"
    grade = None
    for ans in reg_result.get("answers", []):
        name = (ans.get("name") or "").lower()
        if "division" in name:
            val = ans.get("stringValue") or ans.get("arrayValue")
            if isinstance(val, list):
                val = val[0] if val else ""
            if val:
                division = str(val)
        if "grade" in name:
            val = ans.get("stringValue") or ans.get("arrayValue")
            if isinstance(val, list):
                val = val[0] if val else ""
            if val:
                grade = str(val)
    
    # Title Case sport, "Spring 2026" season
    sport = extract_sport_from_registration_name(reg_name)
    season = extract_season_from_registration_name(reg_name)
    
    logger.info(f"Webhook processing: {player_name} for {sport}/{season}, division: {division}, grade: {grade}")
    
    # NAME ONLY matching
    existing_player = None
    normalized_name = " ".join(player_name.lower().split())
    
    existing_player = db.query(Player).filter(Player.full_name == player_name).first()
    
    if not existing_player:
        existing_player = db.query(Player).filter(
            func.lower(Player.full_name) == normalized_name
        ).first()
    
    if existing_player:
        if grade:
            existing_player.grade = grade
        
        # Use year-fallback matching
        existing_reg = _find_existing_registration(db, existing_player.id, sport, season)
        
        if existing_reg:
            if division != "Waiting Room" and existing_reg.division != division:
                existing_reg.division = division
                db.commit()
                logger.info(f"Webhook: Updated division for {existing_player.full_name}: {division}")
                return {"action": "updated_division", "player": existing_player.full_name, "division": division}
            else:
                return {"action": "already_current", "player": existing_player.full_name}
        else:
            try:
                from sqlalchemy.exc import IntegrityError
                new_reg = Registration(
                    player_id=existing_player.id,
                    program=reg_name,
                    division=division,
                    sport=sport,      # Title Case
                    season=season,    # "Spring 2026"
                    confirmation_sent=True
                )
                db.add(new_reg)
                db.commit()
                logger.info(f"Webhook: Added {sport} for {existing_player.full_name}")
                return {"action": "added_sport", "player": existing_player.full_name, "sport": sport}
            except IntegrityError:
                db.rollback()
                logger.info(f"Webhook: Registration already exists for {existing_player.full_name} ({sport})")
                return {"action": "already_exists", "player": existing_player.full_name}
    
    else:
        # NEW PLAYER
        normalized_player_name = " ".join(word.capitalize() for word in player_name.split())
        
        jersey_number = None
        if birth_year:
            jersey_number = assign_jersey_number(db, birth_year)
        
        final_division = division
        if not birth_year or not jersey_number:
            final_division = "Waiting Room"
            logger.info(f"Webhook: Missing data for {normalized_player_name} - placing in Waiting Room")
        
        new_player = Player(
            full_name=normalized_player_name,
            birth_year=birth_year,
            grade=grade,
            jersey_number=jersey_number,
            parent_email=parent_email
        )
        db.add(new_player)
        db.flush()
        
        new_reg = Registration(
            player_id=new_player.id,
            program=reg_name,
            division=final_division,
            sport=sport,          # Title Case
            season=season,        # "Spring 2026"
            confirmation_sent=False
        )
        db.add(new_reg)
        db.commit()
        
        logger.info(f"Webhook: Created new player {normalized_player_name}, jersey #{jersey_number}, division: {final_division}")
        return {"action": "created", "player": normalized_player_name, "jersey": jersey_number, "sport": sport, "division": final_division}

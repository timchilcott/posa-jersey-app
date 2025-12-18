"""
SportsEngine API Integration Service

Handles OAuth authentication, GraphQL queries, and syncing registrations
from SportsEngine to the local database.
"""

import os
import logging
import requests
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
    
    # SportsEngine uses a different query structure
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
            "count": 0  # Registration count not available in this query
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
        
        # Add delay between API calls to avoid rate limiting (max ~60 calls/min)
        if i > 0:
            time.sleep(1.5)  # 1.5 seconds between calls
        
        # Query individual profile for registration results
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
            # Fall back to basic profile data
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
    
    # Return in expected format
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
    Examples:
        "2025 Spring Soccer" -> "soccer"
        "Fall 2025 Basketball Registration" -> "basketball"
        "Pines Volleyball 2025" -> "volleyball"
    """
    name_lower = registration_name.lower()
    
    sports = ["soccer", "basketball", "baseball", "softball", "volleyball", "flag football", "flag"]
    
    for sport in sports:
        if sport in name_lower:
            return sport
    
    # Default fallback
    logger.warning(f"Could not extract sport from registration name: {registration_name}")
    return "unknown"


def extract_season_from_registration_name(registration_name: str) -> str:
    """
    Extract season/year from registration form name.
    Examples:
        "2025 Spring Soccer" -> "2025"
        "Fall 2025 Basketball" -> "2025"
    """
    import re
    
    # Look for 4-digit year
    match = re.search(r'20\d{2}', registration_name)
    if match:
        return match.group(0)
    
    # Default to current year
    return str(datetime.now().year)


def extract_division(answers: list) -> str:
    """
    Extract division from registration answers.
    
    Looks for a field labeled "Division" (case-insensitive) and returns
    its value directly. If not found, returns "Waiting Room".
    
    The Division field in SportsEngine is typically a dropdown with values like:
    - U4, U6, U8, U10, U12, U14
    - High School
    - Pend Oreille Pines (High School Club Team)
    """
    if not answers:
        return "Waiting Room"
    
    for answer in answers:
        question = answer.get("question", {})
        label = (question.get("label") or "").strip().lower()
        value = (answer.get("value") or "").strip()
        
        # Check for Division field (case-insensitive)
        if label in ["division", "age division", "player division", "age group"]:
            if value:
                # Normalize common variations
                value_upper = value.upper()
                if value_upper in ["U3", "U4", "U5", "U6", "U8", "U10", "U12", "U14"]:
                    return value_upper
                if "high school" in value.lower() or "hs" in value.lower():
                    return "Pend Oreille Pines (High School Club Team)"
                # Return as-is if it looks valid
                return value
    
    # No division found
    logger.info("No Division field found in registration answers, placing in Waiting Room")
    return "Waiting Room"


def extract_birth_year(registrant: dict) -> Optional[int]:
    """Extract birth year from registrant's date of birth."""
    dob = registrant.get("dateOfBirth")
    if not dob:
        return None
    
    try:
        # Handle various date formats
        if isinstance(dob, str):
            # Try ISO format first (YYYY-MM-DD)
            if "-" in dob:
                return int(dob.split("-")[0])
            # Try MM/DD/YYYY format
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
    """
    Extract parent/guardian email from registration.
    Prefers guardian email, falls back to registrant email.
    """
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
# Sync Logic
# ---------------------------------------------------------------------
def sync_registration(registration_id: str, db: Session) -> dict:
    """
    Sync all results from a specific SportsEngine registration form.
    
    Returns summary of actions taken.
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
        
        # Extract sport and season from registration form name
        sport = extract_sport_from_registration_name(registration_name)
        season = extract_season_from_registration_name(registration_name)
        
        for reg in nodes:
            try:
                process_single_registration(reg, sport, season, registration_name, db, results)
            except Exception as e:
                logger.error(f"Error processing registration {reg.get('id')}: {e}")
                results["errors"].append(str(e))
        
        # Handle pagination
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
    
    Logic:
    - New player: Create player, assign jersey, create registration, confirmation_sent=False
    - Existing player: Keep jersey, create/update registration, confirmation_sent=True
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
    order_number = reg.get("orderNumber")
    
    # Parse created_at for order_date
    order_date = None
    created_at = reg.get("createdAt")
    if created_at:
        try:
            order_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except:
            pass
    
    # Check if player already exists (by name)
    existing_player = db.query(Player).filter(Player.full_name == player_name).first()
    
    if existing_player:
        # EXISTING PLAYER
        results["existing_players"] += 1
        player = existing_player
        
        # Update birth year if we now have it and they don't
        if birth_year and not player.birth_year:
            player.birth_year = birth_year
        
        # Update parent email if we have a better one
        if parent_email != "unknown@example.com" and player.parent_email == "unknown@example.com":
            player.parent_email = parent_email
        
        # Check if registration for this sport/season already exists
        existing_reg = db.query(Registration).filter(
            Registration.player_id == player.id,
            Registration.sport == sport,
            Registration.season == season
        ).first()
        
        if existing_reg:
            # Update existing registration - but DON'T overwrite manually-set divisions
            # Only update division if:
            # 1. Current division is "Waiting Room" (needs assignment), AND
            # 2. New division is NOT "Waiting Room" (we have actual data)
            if existing_reg.division == "Waiting Room" and division != "Waiting Room":
                existing_reg.division = division
                logger.info(f"Updated division for {player_name}: {division}")
            
            existing_reg.order_number = order_number
            existing_reg.order_date = order_date
            # Keep confirmation_sent as-is for existing registrations
            results["updated_registrations"] += 1
            logger.debug(f"Updated registration for existing player: {player_name}")
        else:
            # New registration for existing player
            # Set confirmation_sent=True because they already have a jersey
            new_reg = Registration(
                player_id=player.id,
                program=program_name,
                division=division,
                sport=sport,
                season=season,
                order_number=order_number,
                order_date=order_date,
                confirmation_sent=True  # Existing player, no email needed
            )
            db.add(new_reg)
            results["new_registrations"] += 1
            logger.info(f"Added new sport registration for existing player: {player_name} ({sport})")
    
    else:
        # NEW PLAYER
        results["new_players"] += 1
        
        # Assign jersey number based on birth year
        jersey_number = None
        if birth_year:
            jersey_number = assign_jersey_number(db, birth_year)
        
        # Create new player
        player = Player(
            full_name=player_name,
            birth_year=birth_year,
            jersey_number=jersey_number,
            parent_email=parent_email
        )
        db.add(player)
        db.flush()  # Get player ID
        
        # Create registration with confirmation_sent=False (needs email)
        new_reg = Registration(
            player_id=player.id,
            program=program_name,
            division=division,
            sport=sport,
            season=season,
            order_number=order_number,
            order_date=order_date,
            confirmation_sent=False  # New player, needs email
        )
        db.add(new_reg)
        results["new_registrations"] += 1
        
        logger.info(f"Created new player: {player_name} (jersey #{jersey_number}, division: {division})")


def sync_all_registrations(db: Session) -> dict:
    """
    Sync all active registration forms from SportsEngine.
    """
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
        # Only sync active/open registrations
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
    
    Only fetches and adds the NEW person, not everyone.
    
    Webhook payload format:
    {
        "organizationId": 12345,
        "resourceOperation": "create" | "update" | "delete",
        "resourceId": "uuid",
        "resourceType": "registration" | "registrationResult" | "profile" | etc.
    }
    """
    resource_type = payload.get("resourceType")
    operation = payload.get("resourceOperation")
    resource_id = payload.get("resourceId")
    org_id = payload.get("organizationId")
    
    # Log full payload so we can debug
    logger.info(f"Webhook FULL payload: {payload}")
    logger.info(f"Webhook parsed: operation={operation}, type={resource_type}, id={resource_id}")
    
    # Only process new registrations
    if operation != "create":
        logger.info(f"Webhook SKIPPED: operation is '{operation}', not 'create'")
        return {"action": "ignored", "reason": f"Not a create: {operation}"}
    
    if resource_type not in ["registrationResult", "profile", "registration_result"]:
        logger.info(f"Webhook SKIPPED: type is '{resource_type}', not registrationResult/profile")
        return {"action": "ignored", "reason": f"Not a registration: {resource_type}"}
    
    logger.info(f"Webhook PROCESSING: {operation} {resource_type} {resource_id}")
    
    try:
        from app.models import Player, Registration
        from app.services.assign import assign_jersey_number
        
        env_org_id = os.getenv("SPORTSENGINE_ORG_ID")
        
        # Handle both profile and registrationResult webhooks
        if resource_type in ["profile", "registrationResult", "registration_result"]:
            # For registrationResult, we need to fetch profile info differently
            # First try to get the profile directly
            profile_query = """
            query GetProfile($profileId: ID!, $orgId: Int!) {
                profile(id: $profileId, organizationId: $orgId) {
                    id
                    firstName
                    lastName
                    dateOfBirth
                    email
                    registrationResults(perPage: 10) {
                        results {
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
            """
            
            logger.info(f"Querying profile with ID: {resource_id}, org: {env_org_id}")
            
            data = graphql_query(profile_query, {
                "profileId": str(resource_id),
                "orgId": int(env_org_id)
            })
            
            logger.info(f"Profile query response: {data}")
            
            profile = data.get("profile")
            if not profile:
                logger.warning(f"Profile not found for ID {resource_id}")
                return {"action": "error", "message": "Profile not found"}
            
            # Get the most recent registration result
            reg_results = profile.get("registrationResults", {}).get("results", [])
            logger.info(f"Found {len(reg_results)} registration results for profile")
            
            if not reg_results:
                logger.warning(f"No registration results for profile {resource_id}")
                return {"action": "ignored", "reason": "No registration results"}
            
            latest_reg = reg_results[0]
            reg_name = latest_reg.get("registrationName", "Unknown")
            
            # Extract data
            player_name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
            birth_year = None
            dob = profile.get("dateOfBirth")
            if dob and "-" in str(dob):
                birth_year = int(str(dob).split("-")[0])
            
            parent_email = (profile.get("email") or "unknown@example.com").lower().strip()
            
            # Extract division from answers
            division = "Waiting Room"
            for ans in latest_reg.get("answers", []):
                name = (ans.get("name") or "").lower()
                if "division" in name:
                    val = ans.get("stringValue") or ans.get("arrayValue")
                    if isinstance(val, list):
                        val = val[0] if val else ""
                    if val:
                        division = str(val)
                    break
            
            # Extract sport from registration name
            sport = extract_sport_from_registration_name(reg_name)
            season = extract_season_from_registration_name(reg_name)
            
            # Check if player already exists
            existing_player = db.query(Player).filter(Player.full_name == player_name).first()
            
            if existing_player:
                # Check if they already have this sport/season
                existing_reg = db.query(Registration).filter(
                    Registration.player_id == existing_player.id,
                    Registration.sport == sport,
                    Registration.season == season
                ).first()
                
                if existing_reg:
                    return {"action": "skipped", "reason": "Already registered", "player": player_name}
                
                # Add new sport for existing player
                new_reg = Registration(
                    player_id=existing_player.id,
                    program=reg_name,
                    division=division,
                    sport=sport,
                    season=season,
                    confirmation_sent=True  # Existing player, no email needed
                )
                db.add(new_reg)
                db.commit()
                
                return {"action": "added_sport", "player": player_name, "sport": sport}
            
            else:
                # NEW PLAYER - assign jersey and create
                jersey = assign_jersey_number(birth_year, db)
                
                new_player = Player(
                    full_name=player_name,
                    birth_year=birth_year,
                    jersey_number=jersey,
                    parent_email=parent_email,
                    locked=False
                )
                db.add(new_player)
                db.flush()
                
                new_reg = Registration(
                    player_id=new_player.id,
                    program=reg_name,
                    division=division,
                    sport=sport,
                    season=season,
                    confirmation_sent=False  # New player needs email
                )
                db.add(new_reg)
                db.commit()
                
                logger.info(f"Webhook added new player: {player_name}, jersey #{jersey}")
                return {"action": "created", "player": player_name, "jersey": jersey, "sport": sport}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return {"action": "error", "message": str(e)}

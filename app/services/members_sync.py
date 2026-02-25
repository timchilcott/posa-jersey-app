"""
SportsEngine Members Directory Sync

Pulls all profiles from the organization with extended data:
- Contact info (email, phone, address)
- Parent/guardian relationships
- Memberships

Two-step approach:
1. List all profiles (returns SimpleProfile with basic fields)
2. Fetch each profile individually (returns full Profile with guardians, address, etc.)
"""

import logging
import time
from sqlalchemy.orm import Session

from app.services.sportsengine import is_configured, get_access_token, graphql_query

logger = logging.getLogger(__name__)


# Step 1 query: list profiles (SimpleProfile type — no guardians/address)
LIST_QUERY = """
query GetMembers($orgId: Int!, $page: Int!) {
    profiles(
        organizationId: $orgId
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
            email
            dateOfBirth
        }
    }
}
"""

# Step 2 query: fetch individual profile (full Profile type — has everything)
DETAIL_QUERY = """
query GetProfile($profileId: Int!, $orgId: Int!) {
    profile(id: $profileId, organizationId: $orgId) {
        id
        firstName
        lastName
        middleName
        preferredName
        suffix
        email
        phone
        dateOfBirth
        gender
        graduationYear
        photoUrl
        address {
            address1
            address2
            city
            state
            postalCode
            country
        }
        memberships {
            name
            status
        }
        parentGuardians {
            firstName
            lastName
            email
            phone
            photoUrl
            type
        }
    }
}
"""


def sync_members(db: Session) -> dict:
    """
    Sync all member profiles from SportsEngine into the members table.
    Step 1: List all profile IDs page by page (SimpleProfile).
    Step 2: Fetch each profile individually for full data (Profile).
    """
    import os
    from app.models_members import Member, MemberGuardian

    if not is_configured():
        raise ValueError("SportsEngine not configured")

    org_id = int(os.getenv("SPORTSENGINE_ORG_ID"))

    results = {
        "new_members": 0,
        "updated_members": 0,
        "guardians_added": 0,
        "pages_processed": 0,
        "profiles_fetched": 0,
        "skipped_existing": 0,
        "errors": [],
    }

    # Collect all known SE profile IDs for incremental sync
    known_ids = set(
        row[0] for row in db.query(Member.se_profile_id).all()
    )
    if known_ids:
        print(f"MEMBERS SYNC: {len(known_ids)} profiles already in DB", flush=True)

    page = 1
    total_pages = None

    while True:
        # Step 1: Get list of profile IDs
        try:
            data = graphql_query(LIST_QUERY, {"orgId": org_id, "page": page})
        except Exception as e:
            logger.error(f"MEMBERS SYNC: List query failed on page {page}: {e}")
            results["errors"].append(f"Page {page}: {str(e)}")
            break

        profiles_data = data.get("profiles", {})
        page_info = profiles_data.get("pageInformation", {})
        profiles = profiles_data.get("results", [])

        if total_pages is None:
            total_pages = page_info.get("pages", 1)
            total_count = page_info.get("count", 0)
            print(f"MEMBERS SYNC: {total_count} total profiles across {total_pages} pages", flush=True)

        print(f"MEMBERS SYNC: Processing page {page}/{total_pages} ({len(profiles)} profiles)", flush=True)

        # Step 2: Fetch full details for each profile
        for i, simple_profile in enumerate(profiles):
            profile_id = simple_profile.get("id")
            if not profile_id:
                continue

            # Skip profiles we already have (incremental sync)
            if int(profile_id) in known_ids:
                results["skipped_existing"] += 1
                continue

            # Rate limit: 1.5s between detail queries
            if results["profiles_fetched"] > 0:
                time.sleep(1.5)

            try:
                detail_data = graphql_query(DETAIL_QUERY, {
                    "profileId": int(profile_id),
                    "orgId": org_id,
                })
                full_profile = detail_data.get("profile")
                if full_profile:
                    _upsert_member(db, full_profile, results)
                    results["profiles_fetched"] += 1
                else:
                    logger.warning(f"MEMBERS SYNC: No data for profile {profile_id}")
            except Exception as e:
                logger.error(f"MEMBERS SYNC: Error fetching profile {profile_id}: {e}", exc_info=True)
                results["errors"].append(f"Profile {profile_id}: {str(e)}")

        results["pages_processed"] += 1
        db.commit()

        if page >= total_pages:
            break

        page += 1
        time.sleep(0.5)  # Rate limit between pages

    print(f"MEMBERS SYNC: Complete — {results}", flush=True)
    return results


def _upsert_member(db: Session, profile: dict, results: dict):
    """Insert or update a single member profile and its guardians."""
    from app.models_members import Member, MemberGuardian

    se_id = int(profile["id"])
    address = profile.get("address") or {}
    memberships_list = profile.get("memberships") or []
    guardians = profile.get("parentGuardians") or []

    # Build memberships string
    membership_names = ", ".join(
        m.get("name", "")
        for m in memberships_list
        if m.get("status") in (None, "ACTIVE", "Active", "active", True)
    ) or None

    # Check for existing member
    existing = db.query(Member).filter(Member.se_profile_id == se_id).first()

    if existing:
        # Update
        existing.first_name = (profile.get("firstName") or "").strip()
        existing.last_name = (profile.get("lastName") or "").strip()
        existing.middle_name = (profile.get("middleName") or "").strip() or None
        existing.preferred_name = (profile.get("preferredName") or "").strip() or None
        existing.suffix = (profile.get("suffix") or "").strip() or None
        existing.email = (profile.get("email") or "").strip() or None
        existing.phone = (profile.get("phone") or "").strip() or None
        existing.date_of_birth = profile.get("dateOfBirth") or None
        existing.gender = profile.get("gender") or None
        existing.graduation_year = profile.get("graduationYear") or None
        existing.photo_url = profile.get("photoUrl") or None
        existing.address1 = (address.get("address1") or "").strip() or None
        existing.address2 = (address.get("address2") or "").strip() or None
        existing.city = (address.get("city") or "").strip() or None
        existing.state = (address.get("state") or "").strip() or None
        existing.postal_code = (address.get("postalCode") or "").strip() or None
        existing.country = (address.get("country") or "").strip() or None
        existing.memberships = membership_names
        member = existing
        results["updated_members"] += 1
    else:
        # Insert
        member = Member(
            se_profile_id=se_id,
            first_name=(profile.get("firstName") or "").strip(),
            last_name=(profile.get("lastName") or "").strip(),
            middle_name=(profile.get("middleName") or "").strip() or None,
            preferred_name=(profile.get("preferredName") or "").strip() or None,
            suffix=(profile.get("suffix") or "").strip() or None,
            email=(profile.get("email") or "").strip() or None,
            phone=(profile.get("phone") or "").strip() or None,
            date_of_birth=profile.get("dateOfBirth") or None,
            gender=profile.get("gender") or None,
            graduation_year=profile.get("graduationYear") or None,
            photo_url=profile.get("photoUrl") or None,
            address1=(address.get("address1") or "").strip() or None,
            address2=(address.get("address2") or "").strip() or None,
            city=(address.get("city") or "").strip() or None,
            state=(address.get("state") or "").strip() or None,
            postal_code=(address.get("postalCode") or "").strip() or None,
            country=(address.get("country") or "").strip() or None,
            memberships=membership_names,
        )
        db.add(member)
        db.flush()  # Get member.id
        results["new_members"] += 1

    # Replace guardians (delete old, insert new)
    db.query(MemberGuardian).filter(MemberGuardian.member_id == member.id).delete()

    for g in guardians:
        guardian = MemberGuardian(
            member_id=member.id,
            first_name=(g.get("firstName") or "").strip(),
            last_name=(g.get("lastName") or "").strip(),
            email=(g.get("email") or "").strip() or None,
            phone=(g.get("phone") or "").strip() or None,
            photo_url=g.get("photoUrl") or None,
            guardian_type=g.get("type") or None,
        )
        db.add(guardian)
        results["guardians_added"] += 1

"""
SportsEngine Members Directory Sync

Pulls all profiles from the organization with extended data:
- Contact info (email, phone, address)
- Parent/guardian relationships
- Memberships
"""

import logging
import time
from sqlalchemy.orm import Session

from app.services.sportsengine import is_configured, get_access_token, graphql_query

logger = logging.getLogger(__name__)


def sync_members(db: Session) -> dict:
    """
    Sync all member profiles from SportsEngine into the members table.
    Pulls profiles page by page with full contact and guardian data.
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
        "errors": [],
    }

    page = 1
    total_pages = None

    while True:
        query = """
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
        }
        """

        try:
            data = graphql_query(query, {"orgId": org_id, "page": page})
        except Exception as e:
            logger.error(f"MEMBERS SYNC: Query failed on page {page}: {e}")
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

        for profile in profiles:
            try:
                _upsert_member(db, profile, results)
            except Exception as e:
                se_id = profile.get("id", "?")
                logger.error(f"MEMBERS SYNC: Error processing profile {se_id}: {e}", exc_info=True)
                results["errors"].append(f"Profile {se_id}: {str(e)}")

        results["pages_processed"] += 1
        db.commit()

        if page >= total_pages:
            break

        page += 1
        time.sleep(0.5)  # Rate limit

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

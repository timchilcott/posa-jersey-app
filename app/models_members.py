"""
Member directory models — stores profile and guardian data from SportsEngine.

These are separate from Player/Registration models. Players are youth athletes
with jersey assignments. Members are the full directory (kids + parents) with
contact details and household relationships.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from datetime import datetime

from .database import Base


class Member(Base):
    """A person in the SportsEngine members directory (child or adult)."""

    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    se_profile_id = Column(Integer, unique=True, nullable=False, index=True)  # SportsEngine profile ID
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    middle_name = Column(String, nullable=True)
    preferred_name = Column(String, nullable=True)
    suffix = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    date_of_birth = Column(String, nullable=True)  # stored as string from API
    gender = Column(String, nullable=True)
    graduation_year = Column(Integer, nullable=True)
    photo_url = Column(String, nullable=True)

    # Address
    address1 = Column(String, nullable=True)
    address2 = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    country = Column(String, nullable=True)

    # Membership info (comma-separated names if multiple)
    memberships = Column(Text, nullable=True)

    # Sync metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_member_name', 'last_name', 'first_name'),
    )


class MemberGuardian(Base):
    """Parent/guardian linked to a member profile."""

    __tablename__ = "member_guardians"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, nullable=False, index=True)  # FK to members.id
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    guardian_type = Column(String, nullable=True)  # e.g. "parent", "guardian"

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_guardian_member', 'member_id'),
    )

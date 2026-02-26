"""
Season Management models — Teams, Rosters, and Staff from SportsEngine.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index
from datetime import datetime
from .database import Base


class Team(Base):
    """A team from SportsEngine Season Management."""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    se_team_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=True)
    sport = Column(String, nullable=True, index=True)
    roster_status = Column(String, nullable=True)
    approved = Column(Boolean, nullable=True)
    logo_url = Column(String, nullable=True)

    # Program info (season/division)
    season_name = Column(String, nullable=True, index=True)    # program.primaryName
    division_name = Column(String, nullable=True, index=True)  # program.secondaryName

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_team_sport_season', 'sport', 'season_name'),
    )


class TeamRoster(Base):
    """A player on a team roster."""
    __tablename__ = "team_roster"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, nullable=False, index=True)
    se_profile_id = Column(Integer, nullable=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    jersey_number = Column(String, nullable=True)
    roster_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_roster_team_profile', 'team_id', 'se_profile_id'),
    )


class TeamStaff(Base):
    """A staff member (coach, manager) on a team."""
    __tablename__ = "team_staff"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, nullable=False, index=True)
    se_profile_id = Column(Integer, nullable=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    roster_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_staff_team', 'team_id'),
    )

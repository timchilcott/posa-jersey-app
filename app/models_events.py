"""
Event models for SportsEngine event tracking (games, practices, events).
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Index, JSON
from datetime import datetime

from .database import Base


class Event(Base):
    """A game, practice, or other event from SportsEngine."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    se_event_id = Column(String, unique=True, nullable=False, index=True)
    organization_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    event_type = Column(String, nullable=False, index=True)  # "game", "practice", "event"
    sport = Column(String, nullable=True, index=True)

    # Times (stored as UTC)
    start_time = Column(DateTime, nullable=True, index=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, nullable=True)  # "scheduled", "completed", "cancelled"
    description = Column(Text, nullable=True)

    # Location
    location_name = Column(String, nullable=True)
    location_address = Column(String, nullable=True)
    location_url = Column(String, nullable=True)
    location_description = Column(String, nullable=True)

    # Teams as JSON array: [{"name": "...", "score": ..., "primaryColor": "...", "homeTeam": true}]
    teams = Column(JSON, nullable=True)

    # SportsEngine timestamps
    se_created_at = Column(DateTime, nullable=True)
    se_updated_at = Column(DateTime, nullable=True)

    # Local timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_event_type_start', 'event_type', 'start_time'),
        Index('ix_event_sport_start', 'sport', 'start_time'),
    )

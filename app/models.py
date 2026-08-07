from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, Boolean, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=True, index=True)
    birth_year = Column(Integer, nullable=True, index=True)
    jersey_number = Column(Integer, nullable=True)
    parent_email = Column(String, nullable=False, index=True)
    is_high_school = Column(Boolean, default=False, nullable=False, index=True)
    locked = Column(Boolean, default=False)

    registrations = relationship("Registration", back_populates="player", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("full_name", name="uq_fullname"),
        Index('ix_player_birth_jersey', 'birth_year', 'jersey_number'),
    )


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)

    program = Column(String, nullable=False)
    division = Column(String, nullable=False, index=True)
    sport = Column(String, nullable=False, index=True)
    season = Column(String, nullable=False, index=True)
    order_number = Column(String, nullable=True)
    order_date = Column(DateTime, nullable=True)

    confirmation_sent = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="registrations")

    __table_args__ = (
        UniqueConstraint("player_id", "sport", "season", name="uq_player_sport_season"),
        Index('ix_registration_season_division', 'season', 'division'),
        Index('ix_registration_sport_season', 'sport', 'season'),
    )


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)


class EmailTemplate(Base):
    """Email template for confirmation emails."""

    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    subject = Column(String, nullable=False)
    body_html = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base  # This is critical!

class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    birth_year = Column(Integer, nullable=True)
    grade = Column(String, nullable=True)  # School grade from registration
    jersey_number = Column(Integer, nullable=True)
    parent_email = Column(String, nullable=False)
    locked = Column(Boolean, default=False)

    registrations = relationship("Registration", back_populates="player", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("full_name", name="uq_fullname"),
    )


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    program = Column(String, nullable=False)
    division = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    season = Column(String, nullable=False)
    order_number = Column(String, nullable=True)
    order_date = Column(DateTime, nullable=True)

    confirmation_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="registrations")

    __table_args__ = (
        UniqueConstraint("player_id", "sport", "season", name="uq_player_sport_season"),
    )


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)


class EmailTemplate(Base):
    """Email template for confirmation emails."""

    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    subject = Column(String, nullable=False)
    body_html = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

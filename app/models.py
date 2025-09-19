from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base  # This is critical!

class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
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


class Sport(Base):
    """Sports available in the system."""

    __tablename__ = "sports"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    divisions = relationship("Division", back_populates="sport", cascade="all, delete-orphan")


class Division(Base):
    """Divisions available for each sport."""

    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    sport_id = Column(Integer, ForeignKey("sports.id"), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    sport = relationship("Sport", back_populates="divisions")

    __table_args__ = (
        UniqueConstraint("sport_id", "name", name="uq_sport_division"),
    )


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

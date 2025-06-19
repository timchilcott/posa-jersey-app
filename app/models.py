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

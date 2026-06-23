"""Player evaluation models for tryouts and development reports."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class EvaluationSession(Base):
    """A tryout or review session tied to one selected SportsEngine registration."""

    __tablename__ = "evaluation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    sport = Column(String, nullable=True, index=True)
    season_name = Column(String, nullable=True, index=True)
    division_name = Column(String, nullable=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)

    # Important guardrail: evaluation imports are scoped to this one selected form.
    sportsengine_registration_id = Column(String, nullable=False, index=True)
    sportsengine_registration_name = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    evaluations = relationship(
        "PlayerEvaluation",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_eval_session_registration", "sportsengine_registration_id"),
    )


class PlayerEvaluation(Base):
    """One evaluator's evaluation for one player in a session."""

    __tablename__ = "player_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("evaluation_sessions.id"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    team_roster_id = Column(Integer, ForeignKey("team_roster.id"), nullable=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True, index=True)

    player_name = Column(String, nullable=False, index=True)
    birth_year = Column(Integer, nullable=True, index=True)
    age_group = Column(String, nullable=True)
    primary_position = Column(String, nullable=True)
    evaluator_name = Column(String, nullable=False)
    future_potential = Column(Float, nullable=True)

    biggest_strength = Column(Text, nullable=True)
    biggest_growth_area = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    submitted = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("EvaluationSession", back_populates="evaluations")
    scores = relationship(
        "EvaluationScore",
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_player_eval_session_player", "session_id", "player_name"),
    )


class EvaluationScore(Base):
    """A single category score for one player evaluation."""

    __tablename__ = "evaluation_scores"

    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(Integer, ForeignKey("player_evaluations.id"), nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)

    evaluation = relationship("PlayerEvaluation", back_populates="scores")

    __table_args__ = (
        UniqueConstraint("evaluation_id", "category", name="uq_evaluation_category_score"),
        Index("ix_score_category", "category"),
    )

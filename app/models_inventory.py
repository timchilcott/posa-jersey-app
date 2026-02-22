"""
Inventory models for equipment tracking.

Add to your existing models.py or import alongside it.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from datetime import datetime

from .database import Base


class InventoryCategory(Base):
    """Category for grouping inventory items (e.g. Balls, Goals, Training Gear)."""

    __tablename__ = "inventory_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    emoji = Column(String, nullable=True)  # e.g. ⚽, 🏀, 🔶
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryItem(Base):
    """A piece of equipment tracked in inventory."""

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)                  # e.g. "Size 4 Soccer Balls"
    category = Column(String, nullable=False)              # e.g. "Balls", "Goals", "Cones"
    sport = Column(String, nullable=True)                  # e.g. "Soccer", "Basketball", or None for general
    quantity_total = Column(Integer, default=0)            # Total owned
    quantity_available = Column(Integer, default=0)        # Currently available (not checked out)
    condition = Column(String, nullable=True)              # "Good", "Fair", "Poor", "New"
    location = Column(String, nullable=True)               # Storage location
    notes = Column(Text, nullable=True)                    # Free-form notes
    min_quantity = Column(Integer, default=0)              # Alert threshold
    cost_per_unit = Column(Float, nullable=True)           # Purchase price per unit
    last_checked = Column(DateTime, nullable=True)         # Last physical count
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

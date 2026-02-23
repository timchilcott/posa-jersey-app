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


class CheckoutRecord(Base):
    """Tracks who checked out what and when."""

    __tablename__ = "checkout_records"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, nullable=False, index=True)  # FK to inventory_items
    person_name = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    checked_out_at = Column(DateTime, default=datetime.utcnow)
    returned_at = Column(DateTime, nullable=True)  # NULL = still checked out
    notes = Column(Text, nullable=True)


class ConditionBreakdown(Base):
    """Tracks condition split for an inventory item (e.g. 20 New, 10 Good, 6 Fair)."""

    __tablename__ = "condition_breakdowns"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, nullable=False, index=True)
    condition = Column(String, nullable=False)  # New, Good, Fair, Poor, Replace
    quantity = Column(Integer, default=0)


class InventoryItem(Base):
    """A piece of equipment tracked in inventory."""

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)                  # e.g. "Size 4 Soccer Balls"
    category = Column(String, nullable=False)              # e.g. "Balls", "Goals", "Cones"
    sport = Column(String, nullable=True)                  # e.g. "Soccer", "Basketball", or None for general
    division = Column(String, nullable=True)               # e.g. "U10", "U12", "Varsity"
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

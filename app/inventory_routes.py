"""
Inventory API Routes

CRUD endpoints for equipment tracking.

Add to main.py:
    from app.inventory_routes import router as inventory_router
    app.include_router(inventory_router)
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models_inventory import InventoryItem, InventoryCategory, CheckoutRecord

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

# ------------------------------------------------------------------
# Default categories (seeded on first request if table is empty)
# ------------------------------------------------------------------
DEFAULT_CATEGORIES = [
    {"name": "Balls", "emoji": "⚽", "sort_order": 1},
    {"name": "Ball Bags", "emoji": "🎒", "sort_order": 2},
    {"name": "Goals", "emoji": "🥅", "sort_order": 3},
    {"name": "Flags", "emoji": "🚩", "sort_order": 4},
    {"name": "Cones", "emoji": "🔶", "sort_order": 5},
    {"name": "Pennies/Bibs", "emoji": "🦺", "sort_order": 6},
    {"name": "Pumps", "emoji": "💨", "sort_order": 7},
    {"name": "Nets", "emoji": "🕸️", "sort_order": 8},
    {"name": "First Aid", "emoji": "🩹", "sort_order": 9},
    {"name": "Other", "emoji": "📦", "sort_order": 99},
]

CONDITIONS = ["New", "Good", "Fair", "Poor", "Replace"]

SPORTS = ["Basketball", "Soccer", "Flag Football", "Volleyball", "POSA"]


def _seed_categories(db: Session):
    """Insert default categories if none exist."""
    if db.query(InventoryCategory).count() == 0:
        for cat in DEFAULT_CATEGORIES:
            db.add(InventoryCategory(**cat))
        db.commit()


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------
@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    _seed_categories(db)
    cats = db.query(InventoryCategory).order_by(InventoryCategory.sort_order).all()
    return {
        "categories": [
            {"id": c.id, "name": c.name, "emoji": c.emoji, "sortOrder": c.sort_order}
            for c in cats
        ]
    }


@router.post("/categories")
async def create_category(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Category name is required")
    existing = db.query(InventoryCategory).filter(
        func.lower(InventoryCategory.name) == name.lower()
    ).first()
    if existing:
        raise HTTPException(400, f"Category '{name}' already exists")
    max_order = db.query(func.max(InventoryCategory.sort_order)).scalar() or 0
    cat = InventoryCategory(
        name=name,
        emoji=data.get("emoji", "📦"),
        sort_order=max_order + 1,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "emoji": cat.emoji}


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(InventoryCategory).filter(InventoryCategory.id == category_id).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    # Don't delete if items still reference it
    item_count = db.query(InventoryItem).filter(
        func.lower(InventoryItem.category) == cat.name.lower()
    ).count()
    if item_count > 0:
        raise HTTPException(400, f"Cannot delete: {item_count} items use this category")
    db.delete(cat)
    db.commit()
    return {"success": True}


# ------------------------------------------------------------------
# Items — List / Filter
# ------------------------------------------------------------------
@router.get("/items")
def list_items(
    category: Optional[str] = None,
    sport: Optional[str] = None,
    condition: Optional[str] = None,
    low_stock: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(InventoryItem)

    if category:
        query = query.filter(func.lower(InventoryItem.category) == category.lower())
    if sport:
        query = query.filter(func.lower(InventoryItem.sport) == sport.lower())
    if condition:
        query = query.filter(func.lower(InventoryItem.condition) == condition.lower())
    if low_stock:
        query = query.filter(InventoryItem.quantity_available <= InventoryItem.min_quantity)
    if search:
        term = f"%{search}%"
        query = query.filter(
            (InventoryItem.name.ilike(term))
            | (InventoryItem.notes.ilike(term))
            | (InventoryItem.location.ilike(term))
        )

    items = query.order_by(InventoryItem.category, InventoryItem.name).all()

    return {
        "count": len(items),
        "items": [_serialize_item(i, db) for i in items],
    }


@router.get("/summary")
def inventory_summary(db: Session = Depends(get_db)):
    """Dashboard summary stats."""
    _seed_categories(db)
    total_items = db.query(func.count(InventoryItem.id)).scalar() or 0
    total_units = db.query(func.coalesce(func.sum(InventoryItem.quantity_total), 0)).scalar()
    available_units = db.query(func.coalesce(func.sum(InventoryItem.quantity_available), 0)).scalar()
    checked_out = total_units - available_units

    low_stock = db.query(func.count(InventoryItem.id)).filter(
        InventoryItem.quantity_available <= InventoryItem.min_quantity,
        InventoryItem.min_quantity > 0,
    ).scalar() or 0

    poor_condition = db.query(func.count(InventoryItem.id)).filter(
        InventoryItem.condition.in_(["Poor", "Replace"])
    ).scalar() or 0

    # Breakdown by category
    cat_rows = db.query(
        InventoryItem.category,
        func.count(InventoryItem.id),
        func.coalesce(func.sum(InventoryItem.quantity_total), 0),
        func.coalesce(func.sum(InventoryItem.quantity_available), 0),
    ).group_by(InventoryItem.category).all()

    categories = []
    for cat_name, count, total, avail in cat_rows:
        # Look up emoji
        cat_obj = db.query(InventoryCategory).filter(
            func.lower(InventoryCategory.name) == cat_name.lower()
        ).first()
        categories.append({
            "name": cat_name,
            "emoji": cat_obj.emoji if cat_obj else "📦",
            "itemCount": count,
            "totalUnits": total,
            "availableUnits": avail,
        })

    return {
        "totalItems": total_items,
        "totalUnits": total_units,
        "availableUnits": available_units,
        "checkedOut": checked_out,
        "lowStock": low_stock,
        "poorCondition": poor_condition,
        "categories": categories,
    }


# ------------------------------------------------------------------
# Items — CRUD
# ------------------------------------------------------------------
@router.post("/items")
async def create_item(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    name = data.get("name", "").strip()
    category = data.get("category", "").strip()
    if not name or not category:
        raise HTTPException(400, "Name and category are required")

    qty_total = int(data.get("quantity_total", 0))
    qty_avail = int(data.get("quantity_available", qty_total))

    item = InventoryItem(
        name=name,
        category=category,
        sport=data.get("sport") or None,
        quantity_total=qty_total,
        quantity_available=qty_avail,
        condition=data.get("condition", "Good"),
        location=data.get("location") or None,
        notes=data.get("notes") or None,
        min_quantity=int(data.get("min_quantity", 0)),
        cost_per_unit=float(data["cost_per_unit"]) if data.get("cost_per_unit") else None,
        last_checked=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_item(item, db)


@router.get("/items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    return _serialize_item(item, db)


@router.put("/items/{item_id}")
async def update_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")

    data = await request.json()

    if "name" in data:
        item.name = data["name"].strip()
    if "category" in data:
        item.category = data["category"].strip()
    if "sport" in data:
        item.sport = data["sport"] or None
    if "quantity_total" in data:
        item.quantity_total = int(data["quantity_total"])
    if "quantity_available" in data:
        item.quantity_available = int(data["quantity_available"])
    if "condition" in data:
        item.condition = data["condition"]
    if "location" in data:
        item.location = data["location"] or None
    if "notes" in data:
        item.notes = data["notes"] or None
    if "min_quantity" in data:
        item.min_quantity = int(data["min_quantity"])
    if "cost_per_unit" in data:
        item.cost_per_unit = float(data["cost_per_unit"]) if data["cost_per_unit"] else None

    db.commit()
    db.refresh(item)
    return _serialize_item(item, db)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    return {"success": True}


# ------------------------------------------------------------------
# Quick actions
# ------------------------------------------------------------------
@router.post("/items/{item_id}/checkout")
async def checkout_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    """Check out equipment to a person."""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    data = await request.json()
    person = (data.get("person_name") or "").strip()
    if not person:
        raise HTTPException(400, "Person name is required")
    qty = int(data.get("quantity", 1))
    if qty > item.quantity_available:
        raise HTTPException(400, f"Only {item.quantity_available} available")
    item.quantity_available -= qty

    record = CheckoutRecord(
        item_id=item.id,
        person_name=person,
        quantity=qty,
        notes=data.get("notes") or None,
    )
    db.add(record)
    db.commit()
    db.refresh(item)
    return _serialize_item(item, db)


@router.post("/items/{item_id}/return")
async def return_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    """Return equipment — either by checkout record id or by quantity."""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    data = await request.json()

    record_id = data.get("record_id")
    if record_id:
        # Return a specific checkout record
        record = db.query(CheckoutRecord).filter(
            CheckoutRecord.id == record_id,
            CheckoutRecord.item_id == item_id,
            CheckoutRecord.returned_at.is_(None),
        ).first()
        if not record:
            raise HTTPException(404, "Active checkout record not found")
        qty = record.quantity
        record.returned_at = datetime.utcnow()
    else:
        # Fallback: return by quantity (legacy)
        qty = int(data.get("quantity", 1))

    new_avail = item.quantity_available + qty
    if new_avail > item.quantity_total:
        raise HTTPException(400, f"Cannot return more than total ({item.quantity_total})")
    item.quantity_available = new_avail
    db.commit()
    db.refresh(item)
    return _serialize_item(item, db)


# ------------------------------------------------------------------
# Checkout records
# ------------------------------------------------------------------
@router.get("/checkouts")
def list_all_checkouts(db: Session = Depends(get_db)):
    """List all active (unreturned) checkouts across all items."""
    records = db.query(CheckoutRecord).filter(
        CheckoutRecord.returned_at.is_(None)
    ).order_by(CheckoutRecord.checked_out_at.desc()).all()
    result = []
    for r in records:
        item = db.query(InventoryItem).filter(InventoryItem.id == r.item_id).first()
        result.append({
            "id": r.id,
            "itemId": r.item_id,
            "itemName": item.name if item else "Unknown",
            "itemCategory": item.category if item else "",
            "personName": r.person_name,
            "quantity": r.quantity,
            "checkedOutAt": r.checked_out_at.isoformat() if r.checked_out_at else None,
            "notes": r.notes,
        })
    return {"checkouts": result}


@router.get("/items/{item_id}/checkouts")
def list_item_checkouts(item_id: int, db: Session = Depends(get_db)):
    """List active checkouts for a specific item."""
    records = db.query(CheckoutRecord).filter(
        CheckoutRecord.item_id == item_id,
        CheckoutRecord.returned_at.is_(None),
    ).order_by(CheckoutRecord.checked_out_at.desc()).all()
    return {
        "checkouts": [
            {
                "id": r.id,
                "personName": r.person_name,
                "quantity": r.quantity,
                "checkedOutAt": r.checked_out_at.isoformat() if r.checked_out_at else None,
                "notes": r.notes,
            }
            for r in records
        ]
    }


@router.post("/items/{item_id}/count")
async def physical_count(item_id: int, request: Request, db: Session = Depends(get_db)):
    """Record a physical count — updates both total and available."""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    data = await request.json()
    counted = int(data.get("counted", 0))
    checked_out = item.quantity_total - item.quantity_available
    item.quantity_total = counted + checked_out
    item.quantity_available = counted
    item.last_checked = datetime.utcnow()
    if "condition" in data:
        item.condition = data["condition"]
    db.commit()
    return _serialize_item(item, db)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _serialize_item(item: InventoryItem, db: Session = None) -> dict:
    checkouts = []
    if db:
        records = db.query(CheckoutRecord).filter(
            CheckoutRecord.item_id == item.id,
            CheckoutRecord.returned_at.is_(None),
        ).order_by(CheckoutRecord.checked_out_at.desc()).all()
        checkouts = [
            {
                "id": r.id,
                "personName": r.person_name,
                "quantity": r.quantity,
                "checkedOutAt": r.checked_out_at.isoformat() if r.checked_out_at else None,
                "notes": r.notes,
            }
            for r in records
        ]

    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "sport": item.sport,
        "quantityTotal": item.quantity_total,
        "quantityAvailable": item.quantity_available,
        "checkedOut": item.quantity_total - item.quantity_available,
        "condition": item.condition,
        "location": item.location,
        "notes": item.notes,
        "minQuantity": item.min_quantity,
        "costPerUnit": item.cost_per_unit,
        "lowStock": (
            item.min_quantity > 0
            and item.quantity_available <= item.min_quantity
        ),
        "lastChecked": item.last_checked.isoformat() if item.last_checked else None,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
        "updatedAt": item.updated_at.isoformat() if item.updated_at else None,
        "checkouts": checkouts,
    }

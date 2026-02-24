"""
Events API Routes — read-only endpoints for displaying SportsEngine events.

Add to main.py:
    from app.events_routes import router as events_router
    app.include_router(events_router)
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models_events import Event

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/items")
def list_events(
    event_type: Optional[str] = None,
    sport: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List events with optional filters, sorted by start_time ascending."""
    query = db.query(Event)

    if event_type:
        query = query.filter(func.lower(Event.event_type) == event_type.lower())
    if sport:
        query = query.filter(func.lower(Event.sport) == sport.lower())
    if status:
        query = query.filter(func.lower(Event.status) == status.lower())
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.filter(Event.start_time >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Event.start_time <= end_dt)
        except ValueError:
            pass
    if search:
        term = f"%{search}%"
        query = query.filter(
            (Event.name.ilike(term))
            | (Event.description.ilike(term))
            | (Event.location_name.ilike(term))
        )

    events = query.order_by(Event.start_time.asc()).all()

    return {
        "count": len(events),
        "events": [_serialize_event(e) for e in events],
    }


@router.get("/summary")
def events_summary(db: Session = Depends(get_db)):
    """Summary stats for the events dashboard."""
    total = db.query(func.count(Event.id)).scalar() or 0
    now = datetime.utcnow()

    upcoming = db.query(func.count(Event.id)).filter(
        Event.start_time > now
    ).scalar() or 0

    past = db.query(func.count(Event.id)).filter(
        Event.start_time <= now
    ).scalar() or 0

    type_counts = db.query(
        Event.event_type, func.count(Event.id)
    ).group_by(Event.event_type).all()

    sport_counts = db.query(
        Event.sport, func.count(Event.id)
    ).filter(Event.sport.isnot(None)).group_by(Event.sport).all()

    return {
        "total": total,
        "upcoming": upcoming,
        "past": past,
        "byType": {t: c for t, c in type_counts},
        "bySport": {s: c for s, c in sport_counts},
    }


def _serialize_event(event: Event) -> dict:
    """Serialize an Event model to a JSON-safe dict."""
    teams = event.teams or []

    home_team = None
    away_team = None
    for t in teams:
        if t.get("homeTeam"):
            home_team = t
        else:
            away_team = t

    return {
        "id": event.id,
        "seEventId": event.se_event_id,
        "name": event.name,
        "eventType": event.event_type,
        "sport": event.sport,
        "startTime": event.start_time.isoformat() + "Z" if event.start_time else None,
        "endTime": event.end_time.isoformat() + "Z" if event.end_time else None,
        "status": event.status,
        "description": event.description,
        "location": {
            "name": event.location_name,
            "address": event.location_address,
            "url": event.location_url,
            "description": event.location_description,
        } if event.location_name else None,
        "teams": teams,
        "homeTeam": home_team,
        "awayTeam": away_team,
        "createdAt": event.created_at.isoformat() if event.created_at else None,
        "updatedAt": event.updated_at.isoformat() if event.updated_at else None,
    }

"""
New Admin API Routes for Drill-Down Interface
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.database import get_db
from app.models import Player, Registration

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/birth-year-groups")
def get_birth_year_groups(db: Session = Depends(get_db)):
    """
    Get all birth years with player counts and stats.
    Returns data for the Level 1 cards view.
    """
    # Get all players grouped by birth year
    birth_year_data = db.query(
        Player.birth_year,
        func.count(Player.id).label('total_count')
    ).group_by(Player.birth_year).all()
    
    groups = []
    current_year = 2026  # Could get from config
    
    for birth_year, total_count in birth_year_data:
        if not birth_year:
            continue
            
        # Count players active in current year (have registrations in 2026)
        active_2026 = db.query(func.count(Player.id.distinct())).join(
            Registration
        ).filter(
            Player.birth_year == birth_year,
            extract('year', Registration.created_at) == current_year
        ).scalar() or 0
        
        # Count players needing emails
        needs_email = db.query(func.count(Player.id.distinct())).join(
            Registration
        ).filter(
            Player.birth_year == birth_year,
            Registration.confirmation_sent == False,
            extract('year', Registration.created_at) == current_year
        ).scalar() or 0
        
        groups.append({
            'year': birth_year,
            'count': total_count,
            'active2026': active_2026,
            'needsEmail': needs_email
        })
    
    # Sort by birth year descending (newest first)
    groups.sort(key=lambda x: x['year'], reverse=True)
    
    return {
        'totalPlayers': sum(g['count'] for g in groups),
        'groups': groups
    }


@router.get("/birth-year/{birth_year}/stats")
def get_birth_year_stats(birth_year: int, db: Session = Depends(get_db)):
    """
    Get detailed stats for a specific birth year.
    Returns data for Level 2 filter view.
    """
    # Total players for this birth year
    total_players = db.query(func.count(Player.id)).filter(
        Player.birth_year == birth_year
    ).scalar()
    
    # Players active in 2026
    active_2026 = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(
        Player.birth_year == birth_year,
        extract('year', Registration.created_at) == 2026
    ).scalar() or 0
    
    # Multi-sport athletes (players with >1 registration in 2026)
    multi_sport = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(
        Player.birth_year == birth_year,
        extract('year', Registration.created_at) == 2026
    ).group_by(Player.id).having(func.count(Registration.id) > 1).count()
    
    # Needs email
    needs_email = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(
        Player.birth_year == birth_year,
        Registration.confirmation_sent == False,
        extract('year', Registration.created_at) == 2026
    ).scalar() or 0
    
    # Available years (years with registrations for this birth year)
    years = db.query(
        extract('year', Registration.created_at).label('year'),
        func.count(Player.id.distinct()).label('count')
    ).join(Player).filter(
        Player.birth_year == birth_year
    ).group_by('year').all()
    
    available_years = [{'value': int(year), 'count': count} for year, count in years if year]
    available_years.sort(key=lambda x: x['value'], reverse=True)
    
    # Available sports
    sports = db.query(
        Registration.sport,
        func.count(Player.id.distinct()).label('count')
    ).join(Player).filter(
        Player.birth_year == birth_year
    ).group_by(Registration.sport).all()
    
    sport_emojis = {
        'Soccer': '⚽',
        'Basketball': '🏀',
        'Flag Football': '🏈',
        'Volleyball': '🏐',
    }
    
    available_sports = [{
        'value': sport.lower().replace(' ', '_') if sport else 'unknown',
        'label': sport or 'Unknown',
        'emoji': sport_emojis.get(sport, '🏃'),
        'count': count
    } for sport, count in sports if sport]
    
    return {
        'stats': {
            'total': total_players,
            'active2026': active_2026,
            'multiSport': multi_sport,
            'needsEmail': needs_email
        },
        'availableYears': available_years,
        'availableSports': available_sports
    }


@router.get("/players")
def get_filtered_players(
    birth_year: Optional[int] = None,
    year: Optional[int] = None,
    sport: Optional[str] = None,
    needs_email: Optional[bool] = None,
    waiting_room: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get filtered list of players with their registrations.
    Returns data for Level 3 player list view.
    """
    # Build query
    query = db.query(Player).join(Registration, isouter=True)
    
    # Apply filters
    if birth_year:
        query = query.filter(Player.birth_year == birth_year)
    
    if year:
        query = query.filter(extract('year', Registration.created_at) == year)
    
    if sport:
        # Normalize sport name
        sport_name = sport.replace('_', ' ').title()
        query = query.filter(Registration.sport == sport_name)
    
    if needs_email is not None:
        query = query.filter(Registration.confirmation_sent == (not needs_email))
    
    if waiting_room:
        query = query.filter(Registration.division == 'Waiting Room')
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Player.full_name.ilike(search_term)) |
            (Player.parent_email.ilike(search_term))
        )
    
    # Get distinct players, ordered youngest to oldest, then jersey # ascending
    from sqlalchemy import case
    players = query.distinct().order_by(
        case((Player.birth_year.is_(None), 1), else_=0),  # nulls last
        Player.birth_year.desc(),
        case((Player.jersey_number.is_(None), 1), else_=0),  # null jerseys last
        Player.jersey_number.asc()
    ).all()
    
    # Format response
    result = []
    for player in players:
        # Get all registrations for this player (filtered by criteria)
        reg_query = db.query(Registration).filter(Registration.player_id == player.id)
        
        if year:
            reg_query = reg_query.filter(extract('year', Registration.created_at) == year)
        if sport:
            sport_name = sport.replace('_', ' ').title()
            reg_query = reg_query.filter(Registration.sport == sport_name)
        
        registrations = reg_query.all()
        
        # Check if any registration has email sent
        email_sent = any(reg.confirmation_sent for reg in registrations)
        
        # Display jersey: show "VOLUNTEER" for locked/volunteer players
        jersey_display = player.jersey_number
        if player.locked:
            jersey_display = "VOLUNTEER"
        
        result.append({
            'id': player.id,
            'name': player.full_name,
            'birthYear': player.birth_year,
            'jersey': jersey_display,
            'email': player.parent_email,
            'emailSent': email_sent,
            'locked': player.locked,
            'registrations': [{
                'id': reg.id,
                'sport': reg.sport,
                'division': reg.division,
                'year': reg.created_at.year if reg.created_at else None,
                'season': reg.season,
                'emailSent': reg.confirmation_sent
            } for reg in registrations]
        })
    
    return {
        'count': len(result),
        'players': result
    }


@router.get("/waiting-room")
def get_waiting_room_players(db: Session = Depends(get_db)):
    """Get all players in waiting room"""
    return get_filtered_players(waiting_room=True, db=db)


@router.get("/needs-email")
def get_needs_email_players(db: Session = Depends(get_db)):
    """Get all players who haven't received confirmation emails"""
    return get_filtered_players(needs_email=True, db=db)


@router.post("/players/{player_id}/send-email")
def send_player_email(player_id: int, db: Session = Depends(get_db)):
    """
    Send confirmation email to a player.
    Can resend even if already sent.
    """
    from app.email import (
        send_confirmation_email,
        send_pines_confirmation_email,
        PROMO_CODES,
    )
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get ALL registrations (including already sent ones - allow resending)
    registrations = db.query(Registration).filter(
        Registration.player_id == player_id
    ).all()
    
    if not registrations:
        return {
            'success': False,
            'message': 'No registrations found'
        }
    
    # Separate Pines HS vs standard registrations
    pines_division = "Pend Oreille Pines (High School Club Team)"
    standard_regs = [r for r in registrations if r.division != pines_division]
    pines_regs = [r for r in registrations if r.division == pines_division]
    
    emails_sent = 0
    
    try:
        # Send standard confirmation for youth divisions
        if standard_regs:
            # Find all players with same parent email to get correct promo code
            sibling_players = db.query(Player).filter(
                Player.parent_email == player.parent_email,
                Player.locked != True  # Exclude volunteers
            ).all()
            sibling_ids = {p.id for p in sibling_players}
            
            # Get all standard registrations for this family
            family_standard_regs = db.query(Registration).filter(
                Registration.player_id.in_(sibling_ids),
                Registration.division != pines_division
            ).all()
            
            # Build player list for email (all siblings with standard regs)
            players_data = []
            family_reg_map = {}  # player_id -> list of regs
            for reg in family_standard_regs:
                family_reg_map.setdefault(reg.player_id, []).append(reg)
            
            for sib in sibling_players:
                sib_regs = family_reg_map.get(sib.id, [])
                if sib_regs:
                    # Use most recent sport for display
                    latest_reg = max(sib_regs, key=lambda r: r.created_at or datetime.min)
                    players_data.append({
                        'name': sib.full_name,
                        'jersey_number': sib.jersey_number,
                        'sport': latest_reg.sport or 'Unknown'
                    })
            
            promo_code = PROMO_CODES.get(len(players_data))
            
            send_confirmation_email(
                to_email=player.parent_email,
                players=players_data,
                promo_code=promo_code,
                registrations=family_standard_regs,
                db=db
            )
            emails_sent += 1
        
        # Send Pines confirmation for HS Club Team
        if pines_regs:
            players_data = [{
                'name': player.full_name,
                'jersey_number': player.jersey_number,
                'sport': reg.sport or 'Unknown'
            } for reg in pines_regs]
            
            send_pines_confirmation_email(
                to_email=player.parent_email,
                players=players_data,
                registrations=pines_regs,
                db=db
            )
            emails_sent += 1
        
        # Mark all as sent (in case the email functions didn't already)
        for reg in registrations:
            reg.confirmation_sent = True
        db.commit()
        
        return {
            'success': True,
            'emailsSent': emails_sent,
            'message': f'Email sent to {player.parent_email}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Failed to send email: {str(e)}'
        }


@router.post("/send-bulk-emails")
def send_bulk_emails(player_ids: List[int], db: Session = Depends(get_db)):
    """Send emails to multiple players"""
    results = []
    for player_id in player_ids:
        try:
            result = send_player_email(player_id, db=db)
            results.append({'playerId': player_id, **result})
        except Exception as e:
            results.append({'playerId': player_id, 'success': False, 'error': str(e)})
    
    success_count = sum(1 for r in results if r.get('success'))
    
    return {
        'total': len(player_ids),
        'success': success_count,
        'failed': len(player_ids) - success_count,
        'results': results
    }


@router.get("/summary")
def get_admin_summary(db: Session = Depends(get_db)):
    """Get overall admin dashboard summary"""
    total_players = db.query(func.count(Player.id)).scalar()
    
    waiting_room = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(Registration.division == 'Waiting Room').scalar() or 0
    
    needs_email = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(Registration.confirmation_sent == False).scalar() or 0
    
    active_2026 = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(extract('year', Registration.created_at) == 2026).scalar() or 0
    
    return {
        'totalPlayers': total_players,
        'waitingRoom': waiting_room,
        'needsEmail': needs_email,
        'active2026': active_2026
    }

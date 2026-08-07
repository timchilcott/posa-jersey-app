"""
New Admin API Routes for Drill-Down Interface
"""
import re
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract, cast, Integer
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.database import get_db
from app.models import Player, Registration
from app.player_dates import date_of_birth_iso, parse_date_of_birth

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Divisions that indicate volunteer/parent (not a player)
VOLUNTEER_DIVISIONS = [
    "Volunteer",
    "Volunteers", 
    "Background Screening",
    "Background Check",
]

def is_volunteer_division(division):
    """Check if a division name indicates a volunteer/parent registration"""
    if not division:
        return False
    d = division.lower()
    return any(v.lower() in d for v in VOLUNTEER_DIVISIONS)


def _season_year(reg):
    """Extract year from season string like '2026' or 'Spring 2026', fall back to created_at."""
    m = re.search(r'20\d{2}', reg.season or '')
    if m:
        return int(m.group())
    return reg.created_at.year if reg.created_at else None


def _season_contains_year(year):
    """SQLAlchemy filter: season field contains the given year (e.g. '2026' matches '2026', 'Spring 2026', 'Fall 2026')."""
    return Registration.season.ilike(f'%{year}%')


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
            
        # Count players active in current year (have registrations with season containing 2026)
        active_2026 = db.query(func.count(Player.id.distinct())).join(
            Registration
        ).filter(
            Player.birth_year == birth_year,
            _season_contains_year(current_year)
        ).scalar() or 0
        
        # Count players needing emails
        needs_email = db.query(func.count(Player.id.distinct())).join(
            Registration
        ).filter(
            Player.birth_year == birth_year,
            Registration.confirmation_sent == False,
            _season_contains_year(current_year)
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
        _season_contains_year(2026)
    ).scalar() or 0
    
    # Multi-sport athletes (players with >1 registration in 2026)
    multi_sport = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(
        Player.birth_year == birth_year,
        _season_contains_year(2026)
    ).group_by(Player.id).having(func.count(Registration.id) > 1).count()
    
    # Needs email
    needs_email = db.query(func.count(Player.id.distinct())).join(
        Registration
    ).filter(
        Player.birth_year == birth_year,
        Registration.confirmation_sent == False,
        _season_contains_year(2026)
    ).scalar() or 0
    
    # Available years - extract year from season field using regex
    # Get all distinct seasons for this birth year, then extract years in Python
    seasons = db.query(
        Registration.season
    ).join(Player).filter(
        Player.birth_year == birth_year
    ).distinct().all()
    
    year_counts = {}
    for (season,) in seasons:
        m = re.search(r'20\d{2}', season or '')
        if m:
            y = int(m.group())
            # Count distinct players for this year
            cnt = db.query(func.count(Player.id.distinct())).join(
                Registration
            ).filter(
                Player.birth_year == birth_year,
                _season_contains_year(y)
            ).scalar() or 0
            year_counts[y] = cnt
    
    available_years = [{'value': y, 'count': c} for y, c in year_counts.items()]
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
    volunteers_only: Optional[bool] = False,
    db: Session = Depends(get_db)
):
    """
    Get filtered list of players with their registrations.
    Returns data for Level 3 player list view.
    """
    # Build query — eager-load registrations in one trip (no N+1)
    query = db.query(Player).options(joinedload(Player.registrations)).join(Registration, isouter=True)

    # Apply filters
    if birth_year:
        query = query.filter(Player.birth_year == birth_year)

    if year:
        query = query.filter(_season_contains_year(year))

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

    # Get distinct players (registrations already loaded via joinedload)
    players = query.distinct().all()

    # A player is a "volunteer" if manually marked (locked=True) OR all their registrations are volunteer divisions
    def player_is_volunteer(p):
        if p.locked:
            return True
        regs = p.registrations
        if not regs:
            return False
        return all(is_volunteer_division(r.division) for r in regs)

    if volunteers_only:
        players = [p for p in players if player_is_volunteer(p)]
    else:
        players = [p for p in players if not player_is_volunteer(p)]

    # Sort: youngest birth year first, then jersey number ascending
    # Nulls go to the end for both fields
    players.sort(key=lambda p: (
        p.birth_year is None,          # nulls last
        -(p.birth_year or 0),          # descending (youngest first)
        p.jersey_number is None,       # null jerseys last
        p.jersey_number or 0           # ascending
    ))

    # Normalize filter values for registration filtering in Python
    sport_name = sport.replace('_', ' ').title() if sport else None
    year_str = str(year) if year else None

    # Format response — use already-loaded registrations, filter in Python
    result = []
    for player in players:
        # Filter registrations in Python from the eager-loaded collection
        registrations = player.registrations
        if year_str:
            registrations = [r for r in registrations if year_str in (r.season or '')]
        if sport_name:
            registrations = [r for r in registrations if r.sport == sport_name]

        # Check if any registration has email sent
        email_sent = any(reg.confirmation_sent for reg in registrations)

        result.append({
            'id': player.id,
            'name': player.full_name,
            'dateOfBirth': date_of_birth_iso(player.date_of_birth),
            'birthYear': player.birth_year,
            'jersey': player.jersey_number,
            'email': player.parent_email,
            'emailSent': email_sent,
            'locked': player.locked,
            'registrations': [{
                'id': reg.id,
                'sport': reg.sport,
                'division': reg.division,
                'year': _season_year(reg),
                'season': reg.season,
                'emailSent': reg.confirmation_sent
            } for reg in registrations]
        })

    return {
        'count': len(result),
        'players': result
    }


@router.post("/players")
def create_player(player_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new player with optional registration."""
    full_name = (player_data.get("full_name") or "").strip()
    parent_email = (player_data.get("parent_email") or "").strip()
    if not full_name or not parent_email:
        raise HTTPException(status_code=400, detail="Name and email are required")

    # Check for duplicate name
    existing = db.query(Player).filter(func.lower(Player.full_name) == full_name.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A player with that name already exists")

    raw_dob = player_data.get("date_of_birth") or player_data.get("dateOfBirth")
    date_of_birth = parse_date_of_birth(raw_dob)
    if raw_dob and not date_of_birth:
        raise HTTPException(status_code=400, detail="Invalid date of birth")

    birth_year = player_data.get("birth_year")
    if date_of_birth:
        birth_year = date_of_birth.year

    player = Player(
        full_name=full_name,
        parent_email=parent_email,
        date_of_birth=date_of_birth,
        birth_year=birth_year,
        jersey_number=player_data.get("jersey_number"),
    )
    db.add(player)
    db.flush()

    # Optionally add a registration
    sport = (player_data.get("sport") or "").strip()
    division = (player_data.get("division") or "").strip()
    season = (player_data.get("season") or "").strip()
    if sport and division and season:
        reg = Registration(
            player_id=player.id,
            program=player_data.get("program", sport),
            sport=sport,
            division=division,
            season=season,
        )
        db.add(reg)

    db.commit()
    return {"id": player.id, "name": player.full_name}


@router.post("/players/{player_id}/registrations")
def add_registration_to_player(
    player_id: int,
    reg_data: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Add a registration to an existing player."""
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    sport = (reg_data.get("sport") or "").strip()
    season = (reg_data.get("season") or "").strip()
    division = (reg_data.get("division") or "").strip()
    if not sport or not season:
        raise HTTPException(status_code=400, detail="sport and season are required")

    # Check for duplicate registration
    existing = db.query(Registration).filter(
        Registration.player_id == player_id,
        func.lower(Registration.sport) == sport.lower(),
        Registration.season == season,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"{player.full_name} already has a {sport}/{season} registration",
        )

    reg = Registration(
        player_id=player.id,
        program=reg_data.get("program", sport),
        sport=sport,
        division=division,
        season=season,
        confirmation_sent=reg_data.get("confirmation_sent", False),
    )
    db.add(reg)
    db.commit()
    return {
        "id": reg.id,
        "player": player.full_name,
        "sport": sport,
        "season": season,
        "division": division,
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

    FIX (Feb 2026):
    - Siblings who have EVER received a confirmation email (any season)
      are excluded entirely — they already have a jersey.
    - Promo code is based only on the players listed in THIS email.
    - Exclude "Unknown" sport entries and deduplicate players.
    """
    from app.email import (
        send_confirmation_email,
        send_pines_confirmation_email,
        PROMO_CODES,
    )
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get this player's registrations
    registrations = db.query(Registration).filter(
        Registration.player_id == player_id
    ).all()
    
    if not registrations:
        return {
            'success': False,
            'message': 'No registrations found'
        }
    
    # ---- Determine the target season from the most recent registration ----
    latest_reg = max(registrations, key=lambda r: r.created_at or datetime.min)
    target_season = latest_reg.season
    
    # Separate Pines HS vs standard registrations (scoped to target season)
    pines_division = "Pend Oreille Pines (High School Club Team)"
    season_regs = [r for r in registrations if r.season == target_season]
    standard_regs = [r for r in season_regs if r.division != pines_division]
    pines_regs = [r for r in season_regs if r.division == pines_division]
    
    emails_sent = 0
    
    try:
        # Send standard confirmation for youth divisions
        if standard_regs:
            # Find all players with same parent email (siblings)
            sibling_players = db.query(Player).filter(
                Player.parent_email == player.parent_email
            ).all()
            
            # ---- KEY FIX: Exclude siblings who have EVER received a
            #      confirmation email (any season). They already have a
            #      jersey and should not appear in this email. ----
            new_siblings = []
            already_have_jersey = []
            for sib in sibling_players:
                all_sib_regs = db.query(Registration).filter(
                    Registration.player_id == sib.id
                ).all()
                ever_confirmed = any(r.confirmation_sent for r in all_sib_regs)
                if ever_confirmed:
                    already_have_jersey.append(sib)
                else:
                    new_siblings.append(sib)
            
            # Mark current-season registrations for skipped siblings as
            # sent so they don't keep showing up as "needs email"
            if already_have_jersey:
                skipped_ids = {p.id for p in already_have_jersey}
                skipped_regs = db.query(Registration).filter(
                    Registration.player_id.in_(skipped_ids),
                    Registration.season == target_season,
                    Registration.confirmation_sent == False,
                ).all()
                for sr in skipped_regs:
                    sr.confirmation_sent = True
            
            new_sibling_ids = {p.id for p in new_siblings}
            
            # Get registrations only for never-confirmed siblings,
            # scoped to the target season, excluding Pines and Unknown sport
            family_standard_regs = db.query(Registration).filter(
                Registration.player_id.in_(new_sibling_ids),
                Registration.division != pines_division,
                Registration.season == target_season,
                Registration.sport != 'Unknown',
                Registration.sport != 'unknown',
                Registration.sport != '',
            ).all() if new_sibling_ids else []
            
            # Build player list for email — deduplicate by player_id
            family_reg_map = {}  # player_id -> list of regs
            for reg in family_standard_regs:
                family_reg_map.setdefault(reg.player_id, []).append(reg)
            
            players_data = []
            seen_player_ids = set()
            for sib in new_siblings:
                if sib.id in seen_player_ids:
                    continue
                sib_regs = family_reg_map.get(sib.id, [])
                if sib_regs:
                    seen_player_ids.add(sib.id)
                    # Use most recent registration's sport for display
                    latest_sib_reg = max(sib_regs, key=lambda r: r.created_at or datetime.min)
                    players_data.append({
                        'name': sib.full_name,
                        'jersey_number': sib.jersey_number,
                        'sport': latest_sib_reg.sport or 'Unknown'
                    })
            
            # Safety filter: drop any remaining Unknown sport entries
            players_data = [
                p for p in players_data
                if p['sport'].lower() != 'unknown'
            ]
            
            # Promo code is based ONLY on players in this email
            if players_data:
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
            
            # Filter out Unknown sport
            players_data = [
                p for p in players_data
                if p['sport'].lower() != 'unknown'
            ]
            
            if players_data:
                send_pines_confirmation_email(
                    to_email=player.parent_email,
                    players=players_data,
                    registrations=pines_regs,
                    db=db
                )
                emails_sent += 1
        
        # Mark registrations in this season as sent
        for reg in season_regs:
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
    ).filter(_season_contains_year(2026)).scalar() or 0
    
    return {
        'totalPlayers': total_players,
        'waitingRoom': waiting_room,
        'needsEmail': needs_email,
        'active2026': active_2026
    }

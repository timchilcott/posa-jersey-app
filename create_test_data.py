#!/usr/bin/env python3
"""Add some test data to see the admin interface with sports and divisions."""

import os
import sys
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

# Set environment variables
os.environ['DATABASE_URL'] = 'sqlite:///test.db'
os.environ['CURRENT_SEASON'] = '2024'

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Player, Registration, Sport, Division

def create_test_data():
    db = SessionLocal()
    
    try:
        # Create sports if they don't exist
        soccer_sport = db.query(Sport).filter(Sport.name == 'soccer').first()
        if not soccer_sport:
            soccer_sport = Sport(name='soccer', display_name='Soccer')
            db.add(soccer_sport)
            db.commit()
            db.refresh(soccer_sport)
        
        basketball_sport = db.query(Sport).filter(Sport.name == 'basketball').first()
        if not basketball_sport:
            basketball_sport = Sport(name='basketball', display_name='Basketball')
            db.add(basketball_sport)
            db.commit()
            db.refresh(basketball_sport)
        
        # Create divisions if they don't exist
        divisions_data = [
            ('U6', 'Under 6', 0),
            ('U8', 'Under 8', 1),
            ('U10', 'Under 10', 2),
            ('U12', 'Under 12', 3),
        ]
        
        for sport in [soccer_sport, basketball_sport]:
            for div_name, div_display, sort_order in divisions_data:
                existing_div = db.query(Division).filter(
                    Division.sport_id == sport.id,
                    Division.name == div_name
                ).first()
                if not existing_div:
                    division = Division(
                        name=div_name,
                        display_name=div_display,
                        sport_id=sport.id,
                        sort_order=sort_order
                    )
                    db.add(division)
        
        db.commit()
        
        # Create some test players and registrations
        players_data = [
            ('John Smith', 'john@example.com', 10, 'soccer', 'U8'),
            ('Jane Doe', 'jane@example.com', 15, 'soccer', 'U10'),
            ('Bob Johnson', 'bob@example.com', 22, 'basketball', 'U12'),
            ('Alice Brown', 'alice@example.com', 5, 'basketball', 'U6'),
        ]
        
        for name, email, jersey, sport_name, division in players_data:
            # Check if player already exists
            existing_player = db.query(Player).filter(Player.full_name == name).first()
            if not existing_player:
                player = Player(
                    full_name=name,
                    parent_email=email,
                    jersey_number=jersey
                )
                db.add(player)
                db.flush()
                
                # Add registration
                registration = Registration(
                    player_id=player.id,
                    program=f"2024 {sport_name.title()}",
                    division=division,
                    sport=sport_name,
                    season="2024"
                )
                db.add(registration)
        
        db.commit()
        print("Test data created successfully!")
        
    finally:
        db.close()

if __name__ == '__main__':
    create_test_data()
from sqlalchemy import create_engine, MetaData, Table

# Use the same DATABASE_URL environment variable as app/database.py.
# For a script within the application package, see app/scripts/add_email_column.py.
DATABASE_URL = "sqlite:///./posa.db"

engine = create_engine(DATABASE_URL)
metadata = MetaData(bind=engine)

# Reflect the existing table
players = Table("players", metadata, autoload_with=engine)

# Add the column if it doesn't already exist
with engine.connect() as conn:
    if "email_sent" not in players.c:
        conn.execute('ALTER TABLE players ADD COLUMN email_sent BOOLEAN DEFAULT 0')
        print("✅ 'email_sent' column added.")
    else:
        print("ℹ️ 'email_sent' column already exists.")


from sqlalchemy import create_engine, MetaData, Table

# Update this path if your database file is somewhere else
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


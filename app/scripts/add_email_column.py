from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.exc import NoSuchTableError

# Path to your SQLite DB
DATABASE_URL = "sqlite:///./app.db"

# Create engine and bind metadata
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

try:
    players_table = Table("players", metadata, autoload_with=engine)

    if "email_sent" not in players_table.columns:
        with engine.connect() as conn:
            conn.execute("ALTER TABLE players ADD COLUMN email_sent BOOLEAN DEFAULT 0")
        print("✅ 'email_sent' column added.")
    else:
        print("ℹ️ 'email_sent' column already exists.")
except NoSuchTableError:
    print("❌ 'players' table not found.")

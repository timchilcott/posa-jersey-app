import logging

from sqlalchemy import inspect, text


logger = logging.getLogger(__name__)


def ensure_player_date_of_birth_column(engine) -> None:
    """Add Player.date_of_birth for existing databases created before this field."""
    inspector = inspect(engine)
    if "players" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("players")}
    if "date_of_birth" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE players ADD COLUMN date_of_birth DATE"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_players_date_of_birth ON players (date_of_birth)")
        )

    logger.info("Added players.date_of_birth column")


def ensure_player_high_school_column(engine) -> None:
    """Add Player.is_high_school for existing databases created before this field."""
    inspector = inspect(engine)
    if "players" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("players")}
    if "is_high_school" in columns:
        return

    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE players ADD COLUMN is_high_school BOOLEAN DEFAULT FALSE NOT NULL")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_players_is_high_school ON players (is_high_school)")
        )

    logger.info("Added players.is_high_school column")


def ensure_player_aliases_table(engine) -> None:
    """Add player aliases table for existing databases created before player merging."""
    inspector = inspect(engine)
    if "players" not in inspector.get_table_names():
        return
    if "player_aliases" in inspector.get_table_names():
        return

    dialect = engine.dialect.name
    id_column = "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "SERIAL PRIMARY KEY"
    created_at_column = "DATETIME DEFAULT CURRENT_TIMESTAMP" if dialect == "sqlite" else "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"

    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS player_aliases (
                id {id_column},
                player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                alias_name VARCHAR NOT NULL,
                normalized_alias VARCHAR NOT NULL,
                created_at {created_at_column}
            )
        """))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_player_aliases_player_id ON player_aliases (player_id)")
        )
        conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_player_aliases_normalized_alias ON player_aliases (normalized_alias)")
        )

    logger.info("Added player_aliases table")

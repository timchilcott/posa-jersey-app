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

"""Install player alias matching into SportsEngine sync."""
import logging

from app.player_aliases import find_player_by_alias

logger = logging.getLogger(__name__)


def install_player_alias_sync_patch() -> None:
    from app.services import sportsengine

    original_find_existing_player = sportsengine._find_existing_player
    if getattr(original_find_existing_player, "_player_alias_patched", False):
        return

    def find_existing_player_with_aliases(db, player_name: str):
        alias_player = find_player_by_alias(db, player_name)
        if alias_player:
            logger.info(
                "SYNC: Player alias match: incoming '%s' matched kept '%s'",
                player_name,
                alias_player.full_name,
            )
            return alias_player

        return original_find_existing_player(db, player_name)

    find_existing_player_with_aliases._player_alias_patched = True
    sportsengine._find_existing_player = find_existing_player_with_aliases

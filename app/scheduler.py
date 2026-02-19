"""
Background scheduler for periodic SportsEngine sync.

Webhooks are the primary mechanism for real-time updates, but they can
be missed (network blips, SportsEngine outages, webhook misconfiguration).
This scheduler acts as a safety net by polling on a configurable interval.

Usage — called from app/main.py lifespan:

    from app.scheduler import start_scheduler, stop_scheduler

    @asynccontextmanager
    async def lifespan(app):
        start_scheduler()
        yield
        stop_scheduler()

Environment variables:
    SYNC_INTERVAL_MINUTES  — polling interval (default 15, set to 0 to disable)
"""

import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

DEFAULT_INTERVAL_MINUTES = 15


def _run_sync() -> None:
    """
    Execute a full SportsEngine sync inside its own DB session.
    Called by APScheduler in a background thread.
    """
    from app.services.sportsengine import is_configured, sync_all_registrations

    if not is_configured():
        logger.debug("Scheduled sync skipped — SportsEngine not configured")
        return

    db = SessionLocal()
    try:
        logger.info("SCHEDULER: Starting periodic SportsEngine sync")
        results = sync_all_registrations(db)
        logger.info(
            "SCHEDULER: Sync complete — new_players=%d, new_regs=%d, updated=%d, errors=%d",
            results["new_players"],
            results["new_registrations"],
            results["updated_registrations"],
            len(results["errors"]),
        )
        if results["errors"]:
            for err in results["errors"][:5]:
                logger.warning("SCHEDULER: sync error: %s", err)
    except Exception:
        logger.exception("SCHEDULER: Periodic sync failed")
    finally:
        db.close()


def start_scheduler() -> None:
    """Start the background polling scheduler."""
    global _scheduler

    interval = int(os.getenv("SYNC_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES))

    if interval <= 0:
        logger.info("SCHEDULER: Disabled (SYNC_INTERVAL_MINUTES=%d)", interval)
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_sync,
        trigger=IntervalTrigger(minutes=interval),
        id="sportsengine_sync",
        name="Periodic SportsEngine sync",
        replace_existing=True,
        next_run_time=None,  # first poll after one full interval
    )

    # Run an initial sync 30s after boot to catch anything missed while down
    from datetime import datetime, timedelta

    _scheduler.add_job(
        _run_sync,
        trigger="date",
        run_date=datetime.now() + timedelta(seconds=30),
        id="sportsengine_initial_sync",
        name="Initial SportsEngine sync on boot",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("SCHEDULER: Started — polling every %d minute(s)", interval)


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("SCHEDULER: Stopped")
        _scheduler = None

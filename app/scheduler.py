import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import get_settings
from app.pipeline.orchestrator import run_pipeline

_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    global _scheduler
    settings = get_settings()
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _trigger,
        trigger="cron",
        hour=settings.run_hour,
        minute=settings.run_minute,
        id="daily_build",
    )
    _scheduler.start()
    print(f"⏰ Scheduler running — daily build at {settings.run_hour:02d}:{settings.run_minute:02d} UTC")


def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown(wait=False)


def get_next_run_time() -> str | None:
    """Return the next scheduled build time as an ISO-8601 string (UTC), or None."""
    if not _scheduler:
        return None
    job = _scheduler.get_job("daily_build")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


async def _trigger():
    await run_pipeline()

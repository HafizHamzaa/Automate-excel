from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .excel_sync import sync_once
from .reports import export_daily_summaries
from .whatsapp_api import send_owner_daily_summary
from .payroll import run_month_end
from .db import init_db

logger = logging.getLogger(__name__)


scheduler: BackgroundScheduler | None = None


def _job_sync_and_prompt():
    # For now only sync; prompts can be added after template approval
    logger.info("06:30 job: Excel sync start")
    try:
        import asyncio

        asyncio.run(sync_once())
    except Exception:
        logger.exception("Excel sync failed")


def _job_daily_reports():
    logger.info("20:00 job: Daily reports")
    paths = export_daily_summaries()
    # Minimal owner text; can be switched to template later
    today = dt.date.today().strftime("%Y-%m-%d")
    msg = f"Daily summaries generated for {today}: {len(paths)} site files."
    import asyncio

    asyncio.run(send_owner_daily_summary(msg))


def _job_month_end():
    now = dt.datetime.now()
    year, month = now.year, now.month
    logger.info("21:00 last-day job: Payroll run for %04d-%02d", year, month)
    out_path = run_month_end(year, month)
    logger.info("Payroll exported to %s", out_path)


def start_jobs() -> None:
    global scheduler
    init_db()
    scheduler = BackgroundScheduler(timezone=settings.timezone)

    # 06:30 every day
    scheduler.add_job(_job_sync_and_prompt, CronTrigger(hour=6, minute=30))

    # 20:00 every day
    scheduler.add_job(_job_daily_reports, CronTrigger(hour=20, minute=0))

    # 21:00 on last day of month
    scheduler.add_job(_job_month_end, CronTrigger(day="last", hour=21, minute=0))

    scheduler.start()
    logger.info("Scheduler started with timezone %s", settings.timezone)
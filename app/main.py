from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import suppress

import uvicorn

from .config import settings
from .db import init_db
from .excel_sync import sync_once
from .scheduler import start_jobs
from .webhook import app as fastapi_app


def setup_logging() -> None:
    os.makedirs("/workspace/logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("/workspace/logs/app.log", encoding="utf-8"),
        ],
    )


async def run_once() -> None:
    await sync_once()


def main() -> None:
    setup_logging()
    init_db()

    # Start scheduler
    start_jobs()

    # Start FastAPI (webhook)
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    asyncio.run(run_once())
    main()
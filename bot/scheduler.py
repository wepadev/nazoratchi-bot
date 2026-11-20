"""Fon jarayoni: muddati tugagan testlarni yopish, eslatmalar, haftalik reyting."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from . import services
from .config import Config
from .db import Database
from .timeutil import utcnow

log = logging.getLogger(__name__)
TICK_SECONDS = 30


async def tick(bot: Bot, db: Database, cfg: Config, now: datetime) -> None:
    for test in await db.due_tests(now):
        await services.close(bot, db, cfg, test, now)
    for lesson in await db.due_lessons(now):
        await services.close_lesson(bot, db, cfg, lesson, now)
    await services.send_reminders(bot, db, cfg, now)
    await services.weekly_rating(bot, db, cfg, now)


async def run(bot: Bot, db: Database, cfg: Config) -> None:
    while True:
        try:
            await tick(bot, db, cfg, utcnow())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler xatosi")
        await asyncio.sleep(TICK_SECONDS)

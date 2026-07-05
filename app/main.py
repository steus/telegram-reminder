"""Точка входа: бот (long polling) + планировщик в одном event loop (§4 ТЗ)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.commands import register_bot_commands
from app.bot.routers import checkin, common, decompose, facilitator, membership, onboarding, profile, tasks
from app.bot.routers import settings as settings_router
from app.config import settings
from app.db.repo import list_all_facilitator_chat_ids
from app.db.session import get_session
from app.scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(membership.router)
    dp.include_router(onboarding.router)
    dp.include_router(profile.router)
    dp.include_router(settings_router.router)
    dp.include_router(facilitator.router)
    dp.include_router(tasks.router)
    dp.include_router(checkin.router)
    dp.include_router(decompose.router)
    dp.include_router(common.router)

    scheduler = create_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    try:
        async with get_session() as session:
            facilitator_ids = await list_all_facilitator_chat_ids(session)
        await register_bot_commands(bot, facilitator_chat_ids=facilitator_ids)

        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting polling")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped by signal")

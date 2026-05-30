"""Планировщик недельных джоб (APScheduler) в общем event loop (§4 ТЗ).

Этап 0: создаём и стартуем пустой scheduler — каркас под будущие джобы
(постановка задач, чек-ин, midweek-пинг появятся на этапах 3+).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.default_timezone)
    # Джобы будут зарегистрированы на следующих этапах.
    return scheduler

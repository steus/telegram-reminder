"""Планировщик недельных джоб (APScheduler) в общем event loop (§4 ТЗ)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.repo import list_active_members
from app.db.session import get_session
from app.services.checkin import mark_scheduler_slot_sent, send_checkin, was_scheduler_slot_sent
from app.services.goal_setup import send_scheduled_goal_setup

logger = logging.getLogger(__name__)

# Одна минутная джоба вместо per-member: проще, переживает рестарт без N записей в job store.
_TICK_JOB_ID = "minute_tick"


def meeting_weekday(checkin_weekday: int) -> int:
    """День встречи: чек-ин накануне → встреча на следующий день недели."""
    return (checkin_weekday + 1) % 7


def slot_key(member_id: int, local_now: datetime, kind: str) -> str:
    return f"{kind}:{member_id}:{local_now.strftime('%Y-%m-%d-%H-%M')}"


def _local_now(member_tz: str) -> datetime:
    try:
        tz = ZoneInfo(member_tz)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz=tz)


def _matches_schedule(local_now: datetime, weekday: int, at_time) -> bool:
    return local_now.weekday() == weekday and (
        local_now.hour == at_time.hour and local_now.minute == at_time.minute
    )


async def _tick(bot: Bot) -> None:
    async with get_session() as session:
        members = await list_active_members(session)

    for member in members:
        local = _local_now(member.timezone)

        if _matches_schedule(local, member.checkin_weekday, member.checkin_time):
            key = slot_key(member.id, local, "checkin")
            async with get_session() as session:
                if await was_scheduler_slot_sent(session, member.id, key):
                    continue
                await mark_scheduler_slot_sent(session, member.id, key)
            try:
                await send_checkin(bot, member)
            except Exception:
                logger.exception("Check-in failed for member_id=%s", member.id)

        meet_wd = meeting_weekday(member.checkin_weekday)
        if _matches_schedule(local, meet_wd, member.checkin_time):
            key = slot_key(member.id, local, "goal_setup")
            async with get_session() as session:
                if await was_scheduler_slot_sent(session, member.id, key):
                    continue
                await mark_scheduler_slot_sent(session, member.id, key)
            try:
                await send_scheduled_goal_setup(bot, member)
            except Exception:
                logger.exception("Goal setup failed for member_id=%s", member.id)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _tick,
        CronTrigger(minute="*"),
        args=[bot],
        id=_TICK_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Scheduler: registered minute tick job (check-in + goal setup per member tz)"
    )
    return scheduler

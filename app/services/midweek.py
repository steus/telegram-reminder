"""Пинг в середине недели — одна невыполненная задача, ответ в один тап (§6.7 ТЗ)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import kb_checkin_task_row
from app.db.models import Member, Task, TaskStatus
from app.db.repo import (
    get_member_by_id,
    get_or_create_current_week,
    list_tasks_for_member_week,
)
from app.db.session import get_session

logger = logging.getLogger(__name__)

MIDWEEK_INTRO = (
    "Середина недели — как дела с этой задачей? "
    "Отметь статус одним тапом, если успел что-то сдвинуть."
)

_OPEN = frozenset({TaskStatus.pending, TaskStatus.in_progress})


def pick_midweek_task(tasks: list[Task]) -> Task | None:
    """Первая подтверждённая задача без финального статуса."""
    for task in tasks:
        if task.confirmed and task.status in _OPEN:
            return task
    return None


def build_midweek_payload(task: Task) -> tuple[str, InlineKeyboardMarkup]:
    short = task.text.strip()
    if len(short) > 120:
        short = short[:117] + "…"
    text = f"{MIDWEEK_INTRO}\n\n«{short}»"
    markup = InlineKeyboardMarkup(inline_keyboard=[kb_checkin_task_row(task)])
    return text, markup


async def load_midweek_task(session: AsyncSession, member: Member) -> Task | None:
    week = await get_or_create_current_week(session, member.group_id)
    tasks = await list_tasks_for_member_week(session, member.id, week.id)
    confirmed = [t for t in tasks if t.confirmed]
    return pick_midweek_task(confirmed if confirmed else tasks)


async def send_midweek_ping(bot: Bot, member: Member) -> bool:
    """Отправить midweek-пинг. True — сообщение ушло."""
    async with get_session() as session:
        member_row = await get_member_by_id(session, member.id)
        if member_row is None or not member_row.is_active or not member_row.midweek_ping:
            return False
        task = await load_midweek_task(session, member_row)
        chat_id = member_row.telegram_chat_id

    if task is None:
        logger.info("Midweek ping skipped: no open tasks for member_id=%s", member.id)
        return False

    text, markup = build_midweek_payload(task)
    await bot.send_message(chat_id, text, reply_markup=markup)
    logger.info("Midweek ping sent to member_id=%s task_id=%s", member.id, task.id)
    return True

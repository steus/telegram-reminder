"""Чек-ин: сообщение, клавиатура, обновление статусов (§6.3–6.4 ТЗ)."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import kb_checkin_message, kb_decompose_offer
from app.bot.task_confirmation import format_task_list
from app.db.models import DialogStateEnum, Member, Task, TaskStatus
from app.db.repo import (
    get_member_by_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    list_tasks_for_member_week,
    set_dialog_state,
    update_task_status,
)
from app.db.session import get_session

logger = logging.getLogger(__name__)

CHECKIN_INTRO = (
    "Как дела с задачами на эту неделю? Отметь статус тапом — "
    "быстро и без лишнего текста."
)

CHECKIN_EMPTY = (
    "На эту неделю задач пока нет — когда появятся, я напомню перед встречей. "
    "Добавить свои — /set_my_goals."
)

CHECKIN_STATUSES = frozenset(
    {TaskStatus.done, TaskStatus.in_progress, TaskStatus.stuck}
)


def checkin_message_text(tasks: list[Task]) -> str:
    if not tasks:
        return CHECKIN_EMPTY
    body = format_task_list(tasks, show_status=True)
    return f"{CHECKIN_INTRO}\n\n{body}"


def build_checkin_payload(tasks: list[Task]) -> tuple[str, InlineKeyboardMarkup | None]:
    text = checkin_message_text(tasks)
    markup = kb_checkin_message(tasks) if tasks else None
    return text, markup


async def apply_status(
    session: AsyncSession, task_id: int, status: TaskStatus
) -> Task | None:
    if status not in CHECKIN_STATUSES:
        return None
    return await update_task_status(session, task_id, status)


async def load_checkin_tasks(
    session: AsyncSession, member: Member
) -> tuple[int, list[Task]]:
    """Задачи текущей недели для чек-ина (подтверждённые, иначе все)."""
    week = await get_or_create_current_week(session, member.group_id)
    tasks = await list_tasks_for_member_week(session, member.id, week.id)
    confirmed = [t for t in tasks if t.confirmed]
    return week.id, confirmed if confirmed else tasks


async def send_checkin(bot: Bot, member: Member) -> bool:
    """Отправить чек-ин участнику. True — сообщение ушло."""
    chat_id: str | None = None
    week_id = 0
    task_count = 0
    text = CHECKIN_EMPTY
    markup: InlineKeyboardMarkup | None = None

    async with get_session() as session:
        member_row = await get_member_by_id(session, member.id)
        if member_row is None or not member_row.is_active:
            return False
        week_id, tasks = await load_checkin_tasks(session, member_row)
        text, markup = build_checkin_payload(tasks)
        task_count = len(tasks)
        await set_dialog_state(session, member_row.id, DialogStateEnum.checkin)
        dialog = await get_or_create_dialog_state(session, member_row.id)
        dialog.active_week_id = week_id
        await session.flush()
        chat_id = member_row.telegram_chat_id

    await bot.send_message(chat_id, text, reply_markup=markup)
    logger.info(
        "Check-in sent to member_id=%s week_id=%s tasks=%s",
        member.id,
        week_id,
        task_count,
    )
    return True


async def on_stuck_status(bot: Bot, chat_id: str | int, task: Task) -> None:
    """Предложить декомпозицию при status=stuck (§6.4)."""
    from app.services.decompose import format_decompose_offer

    await bot.send_message(
        chat_id,
        format_decompose_offer(task),
        reply_markup=kb_decompose_offer(task.id),
    )
    logger.info("Decompose offer sent for task_id=%s", task.id)


def _scheduler_sent_map(context_json: str) -> dict[str, str]:
    try:
        data: dict[str, Any] = json.loads(context_json or "{}")
    except json.JSONDecodeError:
        return {}
    raw = data.get("scheduler_sent")
    return dict(raw) if isinstance(raw, dict) else {}


async def was_scheduler_slot_sent(
    session: AsyncSession, member_id: int, slot_key: str
) -> bool:
    dialog = await get_or_create_dialog_state(session, member_id)
    return _scheduler_sent_map(dialog.context_json).get(slot_key) is not None


async def mark_scheduler_slot_sent(
    session: AsyncSession, member_id: int, slot_key: str
) -> None:
    dialog = await get_or_create_dialog_state(session, member_id)
    try:
        data: dict[str, Any] = json.loads(dialog.context_json or "{}")
    except json.JSONDecodeError:
        data = {}
    sent = _scheduler_sent_map(dialog.context_json)
    sent[slot_key] = slot_key
    data["scheduler_sent"] = sent
    dialog.context_json = json.dumps(data, ensure_ascii=False)
    await session.flush()

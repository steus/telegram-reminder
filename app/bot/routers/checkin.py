"""Чек-ин: callback статусов и /checkin_now (§6.3–6.4 ТЗ)."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.messages import UNKNOWN_USER_TEXT
from app.db.models import TaskStatus
from app.db.repo import get_member_by_chat_id, get_task_by_id
from app.db.session import get_session
from app.services.checkin import (
    apply_status,
    build_checkin_payload,
    load_checkin_tasks,
    on_stuck_status,
    send_checkin,
)

router = Router(name="checkin")

_CALLBACK_RE = re.compile(r"^t:(\d+):(done|in_progress|stuck)$")


def parse_checkin_callback(data: str) -> tuple[int, TaskStatus] | None:
    match = _CALLBACK_RE.match(data)
    if not match:
        return None
    status = TaskStatus(match.group(2))
    return int(match.group(1)), status


@router.message(Command("checkin_now"))
async def cmd_checkin_now(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return

    sent = await send_checkin(message.bot, member)
    if not sent:
        await message.answer("Не удалось отправить чек-ин — напиши ведущему.")


@router.callback_query(F.data.regexp(r"^t:\d+:(done|in_progress|stuck)$"))
async def cb_checkin_status(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    parsed = parse_checkin_callback(callback.data)
    if parsed is None:
        await callback.answer()
        return
    task_id, new_status = parsed

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return

        task = await get_task_by_id(session, task_id)
        if task is None or task.member_id != member.id:
            await callback.answer("Задача не найдена.", show_alert=True)
            return

        if task.status == new_status:
            await callback.answer("Уже отмечено")
            return

        await apply_status(session, task_id, new_status)
        if new_status == TaskStatus.stuck:
            await on_stuck_status(task)

        _, tasks = await load_checkin_tasks(session, member)

    text, markup = build_checkin_payload(tasks)
    await callback.answer("Записал")
    await callback.message.edit_text(text, reply_markup=markup)

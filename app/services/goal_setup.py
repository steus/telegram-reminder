"""Плановый запуск сбора целей после встречи (§6.2, private-ветка)."""

from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dialog_context import DialogContext
from app.db.models import DialogStateEnum, InputMode, Member
from app.db.repo import (
    get_member_by_id,
    get_or_create_dialog_state,
    update_dialog_context,
)
from app.db.session import get_session
from app.services.extraction import GOAL_COLLECTION_PROMPT, start_private_goal_collection

logger = logging.getLogger(__name__)


async def trigger_private_goal_setup(session: AsyncSession, member: Member) -> bool:
    """Запустить private-сбор целей, если участник готов. True — триггер выполнен."""
    if member.input_mode != InputMode.private:
        return False

    dialog = await get_or_create_dialog_state(session, member.id)
    ctx = DialogContext.from_json(dialog.context_json)
    if not ctx.onboarded:
        return False
    if dialog.state == DialogStateEnum.confirming_tasks:
        logger.info("Skip goal setup for member_id=%s — already confirming tasks", member.id)
        return False

    await start_private_goal_collection(session, member)
    ctx.start_task_collection()
    await update_dialog_context(session, member.id, ctx.to_json())
    return True


async def send_scheduled_private_goal_setup(bot: Bot, member: Member) -> bool:
    async with get_session() as session:
        member_row = await get_member_by_id(session, member.id)
        if member_row is None or not member_row.is_active:
            return False
        if not await trigger_private_goal_setup(session, member_row):
            return False
        chat_id = member_row.telegram_chat_id

    await bot.send_message(chat_id, GOAL_COLLECTION_PROMPT)
    logger.info("Goal setup prompt sent to member_id=%s", member.id)
    return True


async def send_scheduled_goal_setup(bot: Bot, member: Member) -> bool:
    """Плановая постановка задач: private или auto в зависимости от input_mode."""
    if member.input_mode == InputMode.auto:
        from app.services.auto_goal_setup import send_scheduled_auto_goal_setup

        return await send_scheduled_auto_goal_setup(bot, member)
    return await send_scheduled_private_goal_setup(bot, member)

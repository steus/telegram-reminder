"""Общий роутер: /help, /stats и подсказки для необработанного аудио."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.dialog_context import DialogContext
from app.bot.filters import HasAudioOnly
from app.bot.messages import UNKNOWN_USER_TEXT
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    list_tasks_with_weeks_for_member,
)
from app.db.session import get_session
from app.services.stats import compute_member_progress, format_stats_message

router = Router(name="common")


@router.message(HasAudioOnly())
async def hint_unhandled_audio(message: Message) -> None:
    """Аудио вне активного диалога — подсказка вместо молчания."""
    from app.services.voice import AUDIO_NOT_IN_DIALOG

    await message.answer(AUDIO_NOT_IN_DIALOG)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    from app.bot.help_text import build_help_text

    await message.answer(await build_help_text(message.chat.id))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        if not ctx.onboarded:
            await message.answer("Сначала давай закончим знакомство — нажми /start.")
            return
        current_week = await get_or_create_current_week(session, member.group_id)
        tasks = await list_tasks_with_weeks_for_member(session, member.id)

    progress = compute_member_progress(tasks, current_week=current_week)
    await message.answer(format_stats_message(progress))

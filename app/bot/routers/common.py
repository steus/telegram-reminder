"""Общий роутер: /help и подсказки для необработанного аудио."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.filters import HasAudioOnly

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


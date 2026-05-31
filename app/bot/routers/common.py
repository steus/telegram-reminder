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
    await message.answer(
        "Что я умею (по мере сборки):\n"
        "/start — знакомство и настройка\n"
        "/setgoals — поставить цели на неделю (private-режим)\n"
        "/tasks — задачи текущей недели\n"
        "/checkin_now — чек-ин вручную (для разработки)\n"
        "/set_plaud_url — ссылка на транскрипт (ведущий)\n"
        "/paste_transcript — вставить транскрипт вручную (ведущий)\n"
        "/stats — твой прогресс по неделям\n"
        "/settings — настройки видимости, времени, пинга\n"
        "/help — это сообщение"
    )

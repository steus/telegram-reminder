"""Общий роутер: /help."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="common")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Что я умею (по мере сборки):\n"
        "/start — знакомство и настройка\n"
        "/setgoals — поставить цели на неделю (private-режим)\n"
        "/tasks — задачи текущей недели\n"
        "/stats — твой прогресс по неделям\n"
        "/settings — настройки видимости, времени, пинга\n"
        "/help — это сообщение"
    )

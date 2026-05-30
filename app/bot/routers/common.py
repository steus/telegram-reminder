"""Общий роутер: /start (заглушка этапа 0) и /help.

Тон сообщений — поддерживающий напарник (§2 ТЗ). Полноценный онбординг
появится на этапе 1 и заменит заглушку /start.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.db.repo import get_member_by_chat_id
from app.db.session import get_session

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)

    if member is None:
        # Полный онбординг придёт на этапе 1; пока — дружелюбное приветствие.
        await message.answer(
            "Привет! Я бот-трекер недельных задач. "
            "Помогаю держать фокус, без лишней рутины. "
            "Полноценный онбординг появится на следующем шаге сборки."
        )
        return

    await message.answer(
        f"С возвращением, {member.full_name}! "
        "Чем помочь сегодня? Загляни в /help."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Что я умею (по мере сборки):\n"
        "/start — знакомство и настройка\n"
        "/tasks — задачи текущей недели\n"
        "/stats — твой прогресс по неделям\n"
        "/settings — настройки видимости, времени, пинга\n"
        "/help — это сообщение"
    )

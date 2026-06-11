"""Меню команд Telegram (/) — описания только «задачи», имена только *_goals."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.bot.command_names import (
    CMD_GOALS,
    CMD_GROUP,
)

_PARTICIPANT_COMMANDS = [
    BotCommand(command=CMD_GOALS, description="Задачи на неделю"),
    BotCommand(command="settings", description="Видимость, время, пинг"),
    BotCommand(command="start", description="Онбординг"),
    BotCommand(command="help", description="Справка по командам"),
]

_FACILITATOR_EXTRA = [
    BotCommand(command=CMD_GROUP, description="Меню ведущего"),
]


async def register_facilitator_commands_for_chat(bot: Bot, chat_id: int) -> None:
    await bot.set_my_commands(
        _PARTICIPANT_COMMANDS + _FACILITATOR_EXTRA,
        scope=BotCommandScopeChat(chat_id=chat_id),
    )


async def register_bot_commands(bot: Bot, *, facilitator_chat_ids: list[int] | None = None) -> None:
    """Зарегистрировать меню / — участникам базовый набор, ведущим расширенный."""
    await bot.set_my_commands(_PARTICIPANT_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    for chat_id in facilitator_chat_ids or []:
        await register_facilitator_commands_for_chat(bot, chat_id)

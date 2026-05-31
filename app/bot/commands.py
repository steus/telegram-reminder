"""Меню команд Telegram (/) — описания только «задачи», имена только *_goals."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.bot.command_names import (
    CMD_GROUP_PASTE_DONE,
    CMD_GROUP_PASTE_TRANSCRIPT,
    CMD_GROUP_SET_PLAUD,
    CMD_GROUP_SYNC_GOALS,
    CMD_GROUP_VIEW_GOALS,
    CMD_SET_MY_GOALS,
    CMD_SYNC_MY_GOALS,
    CMD_VIEW_MY_GOALS,
)

_PARTICIPANT_COMMANDS = [
    BotCommand(command=CMD_SET_MY_GOALS, description="Задать задачи на неделю"),
    BotCommand(command=CMD_VIEW_MY_GOALS, description="Посмотреть задачи и статусы"),
    BotCommand(command=CMD_SYNC_MY_GOALS, description="Обновить задачи в таблице"),
    BotCommand(command="checkin_now", description="Чек-ин вручную (разработка)"),
    BotCommand(command="settings", description="Видимость, время, пинг"),
    BotCommand(command="stats", description="Прогресс по неделям"),
    BotCommand(command="start", description="Онбординг"),
    BotCommand(command="help", description="Справка по командам"),
]

_FACILITATOR_EXTRA = [
    BotCommand(command=CMD_GROUP_PASTE_TRANSCRIPT, description="Вставить «План действий»"),
    BotCommand(command=CMD_GROUP_PASTE_DONE, description="Завершить вставку транскрипта"),
    BotCommand(command=CMD_GROUP_SET_PLAUD, description="Ссылка на Plaud"),
    BotCommand(command=CMD_GROUP_VIEW_GOALS, description="Задачи и статусы группы"),
    BotCommand(command=CMD_GROUP_SYNC_GOALS, description="Обновить задачи группы в таблице"),
]


async def register_bot_commands(bot: Bot, *, facilitator_chat_ids: list[int] | None = None) -> None:
    """Зарегистрировать меню / — участникам базовый набор, ведущим расширенный."""
    await bot.set_my_commands(_PARTICIPANT_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    for chat_id in facilitator_chat_ids or []:
        await bot.set_my_commands(
            _PARTICIPANT_COMMANDS + _FACILITATOR_EXTRA,
            scope=BotCommandScopeChat(chat_id=chat_id),
        )

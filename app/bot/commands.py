"""Меню команд Telegram (/) — описания только «задачи», имена только *_goals."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.bot.command_names import (
    CMD_GROUP_INVITE,
    CMD_GROUP_MEMBERS,
    CMD_GROUP_PASTE_DONE,
    CMD_GROUP_PASTE_TRANSCRIPT,
    CMD_GROUP_REQUESTS,
    CMD_GROUP_SET_PLAUD,
    CMD_GROUP_SYNC_GOALS,
    CMD_GROUP_VIEW_GOALS,
    CMD_MY_GOALS_SET,
    CMD_MY_GOALS_STATS,
    CMD_MY_GOALS_SUBMIT,
    CMD_MY_GOALS_UPDATE,
    CMD_MY_GOALS_VIEW,
)

_PARTICIPANT_COMMANDS = [
    BotCommand(command=CMD_MY_GOALS_SET, description="Задать задачи на неделю"),
    BotCommand(command=CMD_MY_GOALS_VIEW, description="Задачи и статусы на эту неделю"),
    BotCommand(command=CMD_MY_GOALS_UPDATE, description="Обновить статус моих задач"),
    BotCommand(command=CMD_MY_GOALS_STATS, description="Прогресс по неделям"),
    BotCommand(command=CMD_MY_GOALS_SUBMIT, description="Обновить задачи в таблице"),
    BotCommand(command="settings", description="Видимость, время, пинг"),
    BotCommand(command="start", description="Онбординг"),
    BotCommand(command="help", description="Справка по командам"),
]

_FACILITATOR_EXTRA = [
    BotCommand(command=CMD_GROUP_INVITE, description="Ссылка-приглашение в группу"),
    BotCommand(command=CMD_GROUP_MEMBERS, description="Участники и ведущие"),
    BotCommand(command=CMD_GROUP_REQUESTS, description="Заявки на вступление"),
    BotCommand(command=CMD_GROUP_PASTE_TRANSCRIPT, description="Вставить «План действий»"),
    BotCommand(command=CMD_GROUP_PASTE_DONE, description="Завершить вставку транскрипта"),
    BotCommand(command=CMD_GROUP_SET_PLAUD, description="Ссылка на Plaud"),
    BotCommand(command=CMD_GROUP_VIEW_GOALS, description="Задачи и статусы группы"),
    BotCommand(command=CMD_GROUP_SYNC_GOALS, description="Обновить задачи группы в таблице"),
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

"""Текст /help — раздельно для участника и ведущего.

Единообразие: в текстах «задачи», в именах команд — *_goals.
"""

from __future__ import annotations

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
from app.db.repo import get_group_by_facilitator_chat_id
from app.db.session import get_session


async def build_help_text(chat_id: int) -> str:
    lines = [
        "Основное:",
        "/start — онбординг и настройки с нуля",
        "/settings — видимость, время чек-ина, пинг в середине недели",
        "/help — эта справка",
        "",
        "Задачи на неделю:",
        f"/{CMD_MY_GOALS_SET} — задать задачи (режим private)",
        f"/{CMD_MY_GOALS_VIEW} — задачи и статусы на эту неделю",
        f"/{CMD_MY_GOALS_SUBMIT} — обновить задачи в таблице (вкладка «Прогресс»)",
        f"/{CMD_MY_GOALS_UPDATE} — обновить статус моих задач",
        f"/{CMD_MY_GOALS_STATS} — прогресс по неделям (серия, % выполнения)",
    ]

    async with get_session() as session:
        group = await get_group_by_facilitator_chat_id(session, chat_id)
    if group is not None:
        lines.extend(
            [
                "",
                "Ведущий — участники:",
                f"/{CMD_GROUP_INVITE} — ссылка-приглашение в группу",
                f"/{CMD_GROUP_MEMBERS} — список участников и назначение ведущих",
                f"/{CMD_GROUP_REQUESTS} — заявки на вступление",
                "",
                "Ведущий — задачи из транскрипта (Plaud):",
                f"/{CMD_GROUP_PASTE_TRANSCRIPT} — начать вставку «План действий»",
                f"/{CMD_GROUP_PASTE_DONE} — завершить многочастную вставку",
                f"/{CMD_GROUP_SET_PLAUD} — сохранить ссылку на Plaud",
                "",
                "Ведущий — задачи группы:",
                f"/{CMD_GROUP_VIEW_GOALS} — задачи и статусы всех участников",
                f"/{CMD_GROUP_SYNC_GOALS} — обновить задачи всех в таблице",
            ]
        )

    return "\n".join(lines)

"""Текст /help — раздельно для участника и ведущего.

Единообразие: в текстах «задачи», в именах команд — *_goals.
"""

from __future__ import annotations

from app.bot.command_names import (
    CMD_GOALS,
    CMD_GROUP,
    CMD_GROUP_PASTE_DONE,
    CMD_GROUP_PASTE_TRANSCRIPT,
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
        f"/{CMD_GOALS} — меню: задать, посмотреть, статус, прогресс, таблица",
        "",
        "Те же действия отдельными командами:",
        f"/{CMD_MY_GOALS_SET}, /{CMD_MY_GOALS_VIEW}, /{CMD_MY_GOALS_UPDATE}, "
        f"/{CMD_MY_GOALS_STATS}, /{CMD_MY_GOALS_SUBMIT}",
    ]

    async with get_session() as session:
        group = await get_group_by_facilitator_chat_id(session, chat_id)
    if group is not None:
        lines.extend(
            [
                "",
                "Ведущий:",
                f"/{CMD_GROUP} — меню: участники, задачи, транскрипт",
                "",
                "Те же действия отдельными командами:",
                f"/{CMD_GROUP_PASTE_TRANSCRIPT}, /{CMD_GROUP_PASTE_DONE}, "
                f"/{CMD_GROUP_SET_PLAUD}, /{CMD_GROUP_VIEW_GOALS}, /{CMD_GROUP_SYNC_GOALS}",
            ]
        )

    return "\n".join(lines)

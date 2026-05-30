"""Постановка задач: парсинг ввода и запуск сбора целей (§6.2 ТЗ).

На этапе 2 — только правила, без LLM. На этапе 4 `structure_goals` будет
вызывать LLM, а роутер останется прежним.
"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DialogStateEnum, Member
from app.db.repo import get_or_create_current_week, get_or_create_dialog_state, set_dialog_state

_BULLET_RE = re.compile(r"^[\-*•]\s+")
_NUMBERED_RE = re.compile(r"^\d+[\.\)]\s+")


def parse_manual_input(text: str) -> list[str]:
    """Разбить текст на задачи: одна строка / буллет = одна задача."""
    tasks: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = _BULLET_RE.sub("", line)
        line = _NUMBERED_RE.sub("", line).strip()
        if line:
            tasks.append(line)
    return tasks


async def structure_goals(text: str) -> list[str]:
    """Структурировать ввод участника в список задач.

    Точка расширения для LLM (этап 4): заменить тело функции на вызов ask_llm.
    """
    return parse_manual_input(text)


GOAL_COLLECTION_PROMPT = "Какие у тебя цели на эту неделю? Можно списком — каждая строка отдельная задача."

CORRECTION_PROMPT = (
    "Пришли исправленный список — каждая цель с новой строки. "
    "Я пересоберу и покажу ещё раз."
)


async def start_private_goal_collection(session: AsyncSession, member: Member) -> int:
    """Запустить сбор целей в private-режиме. Возвращает week_id."""
    week = await get_or_create_current_week(session, member.group_id)
    dialog = await get_or_create_dialog_state(session, member.id)
    dialog.active_week_id = week.id
    await set_dialog_state(session, member.id, DialogStateEnum.confirming_tasks)
    await session.flush()
    return week.id

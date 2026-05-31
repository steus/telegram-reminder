"""Постановка задач: парсинг ввода, LLM-извлечение (§6.2, §9 ТЗ)."""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import DialogStateEnum, Member
from app.db.repo import get_or_create_current_week, get_or_create_dialog_state, set_dialog_state
from app.llm.client import ask_llm
from app.llm.prompts import PROMPT_EXTRACT_TASKS, PROMPT_STRUCTURE_GOALS
from app.services.plaud_action_plan import extract_tasks_from_action_plan

logger = logging.getLogger(__name__)

_BULLET_RE = re.compile(r"^[\-*•]\s+")
_NUMBERED_RE = re.compile(r"^\d+[\.\)]\s+")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


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


def parse_json_string_array(raw: str) -> list[str]:
    """Безопасно распарсить JSON-массив строк из ответа LLM."""
    cleaned = _FENCE_RE.sub("", raw.strip())
    if not cleaned:
        return []

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON array: %r", raw[:200])
        return []

    if isinstance(data, dict):
        for key in ("tasks", "items", "goals"):
            nested = data.get(key)
            if isinstance(nested, list):
                data = nested
                break
        else:
            return []

    if not isinstance(data, list):
        return []

    result: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _llm_configured() -> bool:
    return bool(settings.llm_provider and settings.llm_model and settings.llm_api_key)


async def structure_goals(text: str) -> list[str]:
    """Структурировать ввод участника в список задач (LLM + фолбэк на правила)."""
    if not _llm_configured():
        return parse_manual_input(text)

    messages = [
        {"role": "system", "content": PROMPT_STRUCTURE_GOALS},
        {"role": "user", "content": text},
    ]
    try:
        raw = await ask_llm(messages, json_mode=True)
        parsed = parse_json_string_array(raw)
        if parsed:
            return parsed
    except Exception:
        logger.warning("LLM structure_goals failed, falling back to rules", exc_info=True)

    return parse_manual_input(text)



def filter_extracted_tasks(
    tasks: list[str],
    full_name: str,
    other_names: list[str],
) -> list[str]:
    """Убрать явно чужие задачи после ответа LLM (консервативный фильтр)."""
    if not tasks:
        return []

    kept: list[str] = []
    for task in tasks:
        tl = task.lower().strip()
        if re.match(r"^(?:speaker|спикер)\s*\d+\s*[:\-—]", tl):
            continue
        skip = False
        for other in other_names:
            ol = other.lower().strip()
            if not ol:
                continue
            first = ol.split()[0]
            if tl.startswith(ol + " ") or tl.startswith(ol + ":"):
                skip = True
                break
            if re.match(
                rf"^{re.escape(first)}\s+(?:должен|надо|провед|сделает|возьм|займёт|займет)",
                tl,
            ):
                skip = True
                break
        if not skip:
            kept.append(task)
    return kept


async def extract_tasks_from_transcript(
    transcript: str,
    full_name: str,
    *,
    other_names: list[str] | None = None,
) -> list[str]:
    """Извлечь задачи участника из транскрипта (Plaud-план → LLM)."""
    plan_tasks = extract_tasks_from_action_plan(transcript, full_name)
    if plan_tasks is not None:
        logger.info(
            "Used Plaud action plan for %s (%d tasks)", full_name, len(plan_tasks)
        )
        return plan_tasks

    if not _llm_configured():
        logger.warning("LLM not configured — cannot extract tasks from transcript")
        return []

    others = other_names or []
    messages = [
        {
            "role": "system",
            "content": PROMPT_EXTRACT_TASKS.format(full_name=full_name),
        },
        {"role": "user", "content": transcript},
    ]
    try:
        raw = await ask_llm(messages, json_mode=True)
        parsed = parse_json_string_array(raw)
        return filter_extracted_tasks(parsed, full_name, others)
    except Exception:
        logger.exception("extract_tasks_from_transcript failed for %s", full_name)
        return []


GOAL_COLLECTION_PROMPT = (
    "Какие у тебя задачи на эту неделю? Можно списком — каждая строка отдельная задача."
)

CORRECTION_PROMPT = (
    "Пришли исправленный список — каждая задача с новой строки. "
    "Я пересоберу и покажу ещё раз."
)

MANUAL_TRANSCRIPT_PROMPT = (
    "Не удалось автоматически получить транскрипт встречи. "
    "Попроси ведущего прислать его командой /group_paste_transcript "
    "или вставь текст сам, если он у тебя есть."
)


async def start_private_goal_collection(session: AsyncSession, member: Member) -> int:
    """Запустить сбор целей в private-режиме. Возвращает week_id."""
    week = await get_or_create_current_week(session, member.group_id)
    dialog = await get_or_create_dialog_state(session, member.id)
    dialog.active_week_id = week.id
    await set_dialog_state(session, member.id, DialogStateEnum.confirming_tasks)
    await session.flush()
    return week.id


async def start_auto_goal_confirmation(session: AsyncSession, member: Member) -> int:
    """Подготовить auto-участника к экрану подтверждения. Возвращает week_id."""
    week = await get_or_create_current_week(session, member.group_id)
    dialog = await get_or_create_dialog_state(session, member.id)
    dialog.active_week_id = week.id
    await set_dialog_state(session, member.id, DialogStateEnum.confirming_tasks)
    await session.flush()
    return week.id

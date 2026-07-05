"""Декомпозиция задачи по согласию (§6.4, промпт 2)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dialog_context import DialogContext
from app.bot.task_confirmation import format_task_list
from app.db.models import DialogStateEnum, Member, Task, Week
from app.db.repo import (
    create_decomposed_subtasks,
    get_or_create_dialog_state,
    get_or_create_next_week,
    get_or_create_profile,
    get_task_by_id,
    set_dialog_state,
    update_dialog_context,
)
from app.llm.client import ask_llm
from app.llm.prompts import PROMPT_DECOMPOSE_STEPS, build_profile_context
from app.services.extraction import parse_json_string_array

logger = logging.getLogger(__name__)

DECOMPOSE_OFFER = (
    "Вижу затык по задаче «{task}». "
    "Помочь разбить её на 2–4 конкретных шага на следующую неделю?"
)
DECOMPOSE_DECLINED = (
    "Ок, оставляем как есть. Если передумаешь — напиши или отметь снова."
)
DECOMPOSE_CONFIRM_PROMPT = (
    "Вот шаги на следующую неделю — проверь, всё ли так:\n\n{steps}\n\n"
    "Если ок — подтверди. Если нужно поправить — пришли исправленный список "
    "(каждый шаг с новой строки)."
)
DECOMPOSE_SAVED = (
    "Зафиксировал шаги на следующую неделю. Исходную задачу отметил как разобранную."
)
DECOMPOSE_NO_STEPS = (
    "Не смог собрать шаги из ответа. Попробуй списком — каждый шаг с новой строки."
)


def format_decompose_offer(task: Task) -> str:
    text = task.text.strip()
    if len(text) > 120:
        text = f"{text[:117]}..."
    return DECOMPOSE_OFFER.format(task=text)


def format_steps_confirmation(steps: list[str]) -> str:
    numbered = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, start=1))
    return DECOMPOSE_CONFIRM_PROMPT.format(steps=numbered)


async def start_decompose_flow(
    session: AsyncSession,
    member: Member,
    task: Task,
) -> str:
    """Запустить декомпозицию: state=decomposing, LLM предлагает шаги."""
    await set_dialog_state(session, member.id, DialogStateEnum.decomposing)
    dialog = await get_or_create_dialog_state(session, member.id)
    ctx = DialogContext.from_json(dialog.context_json)
    ctx.start_decompose(task.id)
    await update_dialog_context(session, member.id, ctx.to_json())

    profile = await get_or_create_profile(session, member.id)
    profile_ctx = build_profile_context(profile.profile_json)
    system = PROMPT_DECOMPOSE_STEPS.format(
        profile=profile_ctx,
        task_text=task.text,
    )
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "Участник согласился на помощь. Предложи шаги.",
        },
    ]
    raw = await ask_llm(messages, json_mode=True)
    steps = parse_json_string_array(raw)
    if not steps:
        # Возможен уточняющий вопрос вместо JSON
        question = raw.strip()
        if question:
            ctx.append_checkin_message("assistant", question)
            await update_dialog_context(session, member.id, ctx.to_json())
            return question
        return DECOMPOSE_NO_STEPS

    ctx.set_decompose_steps(steps)
    await update_dialog_context(session, member.id, ctx.to_json())
    return format_steps_confirmation(steps)


async def continue_decompose_dialog(
    session: AsyncSession,
    member: Member,
    user_text: str,
) -> str:
    """Продолжить диалог декомпозиции (ответ на уточняющий вопрос или правка)."""
    dialog = await get_or_create_dialog_state(session, member.id)
    ctx = DialogContext.from_json(dialog.context_json)
    task_id = ctx.decompose_task_id
    if task_id is None:
        return DECOMPOSE_NO_STEPS

    task = await get_task_by_id(session, task_id)
    if task is None:
        return "Не нашёл задачу для декомпозиции."

    manual_steps = _lines_to_steps(user_text)
    if ctx.decompose_steps is not None or ctx.decompose_awaiting_edit:
        if manual_steps:
            ctx.set_decompose_steps(manual_steps)
            await update_dialog_context(session, member.id, ctx.to_json())
            return format_steps_confirmation(manual_steps)
        if ctx.decompose_awaiting_edit:
            return DECOMPOSE_NO_STEPS

    ctx.append_checkin_message("user", user_text)
    history = ctx.checkin_messages or []
    profile = await get_or_create_profile(session, member.id)
    profile_ctx = build_profile_context(profile.profile_json)
    messages = [
        {
            "role": "system",
            "content": PROMPT_DECOMPOSE_STEPS.format(
                profile=profile_ctx,
                task_text=task.text,
            ),
        },
        *history,
    ]
    raw = await ask_llm(messages, json_mode=True)
    steps = parse_json_string_array(raw)
    if steps:
        ctx.set_decompose_steps(steps)
        await update_dialog_context(session, member.id, ctx.to_json())
        return format_steps_confirmation(steps)

    reply = raw.strip() or DECOMPOSE_NO_STEPS
    ctx.append_checkin_message("assistant", reply)
    await update_dialog_context(session, member.id, ctx.to_json())
    return reply


def _lines_to_steps(text: str) -> list[str]:
    from app.services.extraction import parse_manual_input

    return parse_manual_input(text)


async def confirm_decomposed_steps(
    session: AsyncSession,
    member: Member,
    current_week: Week,
) -> tuple[str, list[Task]]:
    dialog = await get_or_create_dialog_state(session, member.id)
    ctx = DialogContext.from_json(dialog.context_json)
    task_id = ctx.decompose_task_id
    steps = ctx.decompose_steps or []

    if task_id is None or not steps:
        return DECOMPOSE_NO_STEPS, []

    parent = await get_task_by_id(session, task_id)
    if parent is None or parent.member_id != member.id:
        return "Задача не найдена.", []

    next_week = await get_or_create_next_week(session, member.group_id, current_week)
    subtasks = await create_decomposed_subtasks(
        session,
        member_id=member.id,
        parent_task=parent,
        next_week_id=next_week.id,
        step_texts=steps,
    )

    await set_dialog_state(session, member.id, DialogStateEnum.checkin)
    ctx.clear_decompose()
    ctx.clear_checkin_messages()
    await update_dialog_context(session, member.id, ctx.to_json())

    summary = (
        f"{DECOMPOSE_SAVED}\n\n"
        f"Шаги на неделю с {next_week.start_date.strftime('%d.%m.%Y')}:\n"
        f"{format_task_list(subtasks)}"
    )
    return summary, subtasks

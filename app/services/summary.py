"""Итог недели: разбор [REPORT_READY], подтверждение, маршрутизация (§6.5 ТЗ)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dialog_context import DialogContext
from app.bot.keyboards import VISIBILITY_LABELS
from app.db.models import (
    DialogStateEnum,
    Member,
    SharedScope,
    Task,
    TaskStatus,
    Visibility,
    Week,
)
from app.db.repo import (
    create_summary,
    get_group,
    get_or_create_dialog_state,
    list_group_facilitator_chat_ids,
    set_dialog_state,
    update_dialog_context,
)
from app.services.sheets import append_group_summary
from app.services.tracking import strip_machine_markers

logger = logging.getLogger(__name__)

_REPORT_MARKER = "[REPORT_READY]"

_STATUS_ICONS = {
    TaskStatus.done: "✅",
    TaskStatus.in_progress: "🔄",
    TaskStatus.stuck: "⛔",
    TaskStatus.decomposed: "📎",
    TaskStatus.pending: "⏳",
}


@dataclass
class ParsedReport:
    member_text: str
    facilitator_text: str


def split_report_ready(raw: str) -> tuple[str, str]:
    """Диалог до маркера; всё после маркера — резюме для ведущего."""
    idx = raw.find(_REPORT_MARKER)
    if idx == -1:
        return strip_machine_markers(raw), ""
    dialog = strip_machine_markers(raw[:idx])
    facilitator = raw[idx + len(_REPORT_MARKER) :].strip()
    return dialog, facilitator


def build_summary_texts(
    member: Member, tasks: list[Task], raw_llm: str
) -> ParsedReport:
    _dialog, facilitator_part = split_report_ready(raw_llm)
    member_body = facilitator_part or _fallback_member_text(tasks)
    member_text = f"Вот твой итог недели, {member.full_name}:\n\n{member_body}"
    facilitator_text = facilitator_part or member_body
    return ParsedReport(member_text=member_text, facilitator_text=facilitator_text)


def _fallback_member_text(tasks: list[Task]) -> str:
    if not tasks:
        return "На этой неделе задач не было — но ты всё равно заглянул, и это уже шаг."
    lines = ["Кратко по задачам:"]
    for task in tasks:
        icon = _STATUS_ICONS.get(task.status, "•")
        lines.append(f"{icon} {task.text}")
    return "\n".join(lines)


def visibility_to_shared_scope(visibility: Visibility, *, confirmed: bool) -> SharedScope:
    if not confirmed:
        return SharedScope.none
    if visibility == Visibility.group:
        return SharedScope.group
    if visibility == Visibility.facilitator:
        return SharedScope.facilitator
    return SharedScope.private


def summary_confirm_prompt(visibility: Visibility) -> str:
    label = VISIBILITY_LABELS[visibility]
    return (
        "Отправить итог по твоим настройкам видимости?\n"
        f"Сейчас выбрано: {label}.\n\n"
        "До подтверждения никуда не уйдёт — только ты видишь текст выше."
    )


async def store_pending_summary(
    session: AsyncSession,
    member_id: int,
    *,
    week_id: int,
    member_text: str,
    facilitator_text: str,
) -> None:
    dialog = await get_or_create_dialog_state(session, member_id)
    ctx = DialogContext.from_json(dialog.context_json)
    ctx.set_pending_summary(
        week_id=week_id,
        member_text=member_text,
        facilitator_text=facilitator_text,
    )
    await update_dialog_context(session, member_id, ctx.to_json())


async def clear_pending_summary(session: AsyncSession, member_id: int) -> None:
    dialog = await get_or_create_dialog_state(session, member_id)
    ctx = DialogContext.from_json(dialog.context_json)
    ctx.clear_pending_summary()
    ctx.clear_checkin_messages()
    await update_dialog_context(session, member_id, ctx.to_json())
    await set_dialog_state(session, member_id, DialogStateEnum.idle)


async def finalize_summary(
    session: AsyncSession,
    bot: Bot,
    member: Member,
    *,
    week_id: int,
    member_text: str,
    facilitator_text: str,
    send: bool,
) -> SharedScope:
    """Сохранить summary и при send=True маршрутизировать по visibility."""
    if send:
        shared_scope = visibility_to_shared_scope(member.visibility, confirmed=True)
    else:
        shared_scope = SharedScope.none

    await create_summary(
        session,
        member_id=member.id,
        week_id=week_id,
        member_text=member_text,
        facilitator_text=facilitator_text,
        shared_scope=shared_scope,
    )

    if not send:
        return shared_scope

    group = await get_group(session, member.group_id)
    if group is None:
        return shared_scope

    week = await session.get(Week, week_id)
    week_start = week.start_date if week else None

    if shared_scope == SharedScope.group and week_start is not None:
        await append_group_summary(
            group.sheet_id,
            week_start=week_start,
            member_name=member.full_name,
            member_text=member_text,
            facilitator_text=facilitator_text,
        )
    elif shared_scope == SharedScope.facilitator:
        message = (
            f"Итог недели — {member.full_name}\n\n"
            f"{facilitator_text}"
        )
        chat_ids = await list_group_facilitator_chat_ids(session, member.group_id)
        if not chat_ids and group.facilitator_chat_id:
            chat_ids = [group.facilitator_chat_id]
        for chat_id in chat_ids:
            try:
                await bot.send_message(chat_id, message)
            except Exception:
                logger.exception(
                    "Failed to send summary to facilitator chat_id=%s", chat_id
                )

    return shared_scope

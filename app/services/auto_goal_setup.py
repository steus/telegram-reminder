"""Плановый запуск auto-извлечения задач из транскрипта (§6.2, auto-ветка)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dialog_context import DialogContext
from app.bot.task_confirmation import confirmation_message, kb_task_confirmation
from app.db.models import DialogStateEnum, InputMode, Member, TaskSource, Week
from app.db.repo import (
    get_member_by_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    list_auto_members_for_group,
    list_group_member_names,
    list_tasks_for_member_week,
    replace_tasks,
    update_dialog_context,
)
from app.db.session import get_session
from app.services.extraction import (
    MANUAL_TRANSCRIPT_PROMPT,
    extract_tasks_from_transcript,
    start_auto_goal_confirmation,
)
from app.services.plaud import PlaudManualRequired, fetch_transcript

logger = logging.getLogger(__name__)

NO_TASKS_MESSAGE = (
    "Я просмотрел транскрипт, но не нашёл задач, которые можно уверенно "
    "приписать тебе. Если что-то упустил — напиши список вручную через /setgoals "
    "или попроси ведущего проверить транскрипт."
)

REASON_NO_TASKS = "задачи в транскрипте не найдены"
REASON_NOT_ONBOARDED = "не завершил онбординг"
REASON_ALREADY_CONFIRMING = "уже на экране подтверждения (не обновлено — выбери «Разослать участникам» при повторной вставке)"


@dataclass
class AutoExtractionResult:
    sent_with_tasks: list[str] = field(default_factory=list)
    without_tasks: list[tuple[str, str]] = field(default_factory=list)
    no_auto_members: bool = False


def format_facilitator_report(result: AutoExtractionResult, *, saved_only: bool = False) -> str:
    if saved_only:
        return (
            "Транскрипт сохранён. Участникам ничего не отправлено.\n"
            "Чтобы разослать позже — снова /paste_transcript (текст можно тот же) "
            "и выбери «Разослать участникам»."
        )

    lines = ["Транскрипт сохранён."]
    if result.no_auto_members:
        lines.append("Нет участников в режиме auto — некому отправлять.")
    elif result.sent_with_tasks:
        names = ", ".join(result.sent_with_tasks)
        lines.append(
            f"Экран подтверждения отправлен ({len(result.sent_with_tasks)}): {names}."
        )
    if result.without_tasks:
        lines.append("Не удалось назначить задачи:")
        for name, reason in result.without_tasks:
            lines.append(f"  • {name} — {reason}")
    elif not result.no_auto_members and not result.sent_with_tasks:
        lines.append("Никому не отправлено — проверь режим auto и онбординг участников.")
    return "\n".join(lines)


async def has_pending_auto_confirmations(
    session: AsyncSession, group_id: int, week_id: int
) -> bool:
    """Есть ли auto-участники на экране подтверждения задач этой недели."""
    for member in await list_auto_members_for_group(session, group_id):
        dialog = await get_or_create_dialog_state(session, member.id)
        if dialog.active_week_id != week_id:
            continue
        if dialog.state != DialogStateEnum.confirming_tasks:
            continue
        ctx = DialogContext.from_json(dialog.context_json)
        if ctx.task_step in ("confirm", "collect"):
            return True
    return False


async def should_confirm_resend(
    session: AsyncSession,
    group_id: int,
    week_id: int,
    *,
    had_transcript: bool,
) -> bool:
    """Спросить ведущего перед повторной рассылкой после правки транскрипта."""
    if not had_transcript:
        return False
    return await has_pending_auto_confirmations(session, group_id, week_id)


async def trigger_auto_goal_setup(
    session: AsyncSession,
    member: Member,
    week: Week,
    *,
    force: bool = False,
) -> tuple[bool, str | None]:
    """Извлечь задачи из транскрипта. (True, reason) — обработан; (False, reason) — пропуск."""
    if member.input_mode != InputMode.auto:
        return False, "not_auto"

    dialog = await get_or_create_dialog_state(session, member.id)
    ctx = DialogContext.from_json(dialog.context_json)
    if not ctx.onboarded:
        return False, "not_onboarded"
    if not force and dialog.state == DialogStateEnum.confirming_tasks:
        logger.info("Skip auto goal setup for member_id=%s — already confirming", member.id)
        return False, "already_confirming"

    try:
        transcript = await fetch_transcript(week)
    except PlaudManualRequired:
        return False, "manual_required"

    texts = await extract_tasks_from_transcript(
        transcript,
        member.full_name,
        other_names=await list_group_member_names(
            session, member.group_id, exclude_member_id=member.id
        ),
    )
    week_id = await start_auto_goal_confirmation(session, member)

    if texts:
        await replace_tasks(
            session,
            member_id=member.id,
            week_id=week_id,
            texts=texts,
            source=TaskSource.plaud,
        )
        ctx.show_task_confirmation()
        await update_dialog_context(session, member.id, ctx.to_json())
        return True, "tasks_found"

    ctx.start_task_collection()
    await update_dialog_context(session, member.id, ctx.to_json())
    return True, "no_tasks"


async def _notify_member(
    bot: Bot,
    session: AsyncSession,
    member: Member,
    week: Week,
    reason: str,
) -> None:
    chat_id = member.telegram_chat_id
    if reason == "no_tasks":
        await bot.send_message(chat_id, NO_TASKS_MESSAGE)
        logger.info("Auto goal setup: no tasks for member_id=%s", member.id)
        return
    if reason != "tasks_found":
        return
    tasks = await list_tasks_for_member_week(session, member.id, week.id)
    await bot.send_message(
        chat_id,
        confirmation_message(tasks),
        reply_markup=kb_task_confirmation(week.id),
    )
    logger.info("Auto goal setup confirmation sent to member_id=%s", member.id)


async def run_auto_extraction_for_group(
    session: AsyncSession,
    bot: Bot,
    group_id: int,
    *,
    force: bool = False,
) -> AutoExtractionResult:
    """Извлечь задачи для всех auto-участников и разослать экран подтверждения."""
    week = await get_or_create_current_week(session, group_id)
    members = await list_auto_members_for_group(session, group_id)
    result = AutoExtractionResult(no_auto_members=not members)

    for member in members:
        ok, reason = await trigger_auto_goal_setup(
            session, member, week, force=force
        )
        if not ok:
            if reason == "not_onboarded":
                result.without_tasks.append((member.full_name, REASON_NOT_ONBOARDED))
            elif reason == "already_confirming":
                result.without_tasks.append((member.full_name, REASON_ALREADY_CONFIRMING))
            continue

        if reason == "no_tasks":
            await _notify_member(bot, session, member, week, reason)
            result.without_tasks.append((member.full_name, REASON_NO_TASKS))
            continue
        if reason == "tasks_found":
            await _notify_member(bot, session, member, week, reason)
            result.sent_with_tasks.append(member.full_name)

    return result


async def send_scheduled_auto_goal_setup(bot: Bot, member: Member) -> bool:
    async with get_session() as session:
        member_row = await get_member_by_id(session, member.id)
        if member_row is None or not member_row.is_active:
            return False
        if member_row.input_mode != InputMode.auto:
            return False

        week = await get_or_create_current_week(session, member_row.group_id)
        ok, reason = await trigger_auto_goal_setup(session, member_row, week)
        if not ok:
            if reason == "manual_required":
                chat_id = member_row.telegram_chat_id
                await bot.send_message(chat_id, MANUAL_TRANSCRIPT_PROMPT)
                logger.info(
                    "Auto goal setup: manual transcript requested for member_id=%s",
                    member.id,
                )
                return True
            return False

        await _notify_member(bot, session, member_row, week, reason or "")
        return reason in ("tasks_found", "no_tasks")

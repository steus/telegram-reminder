"""Чек-ин: callback статусов, текст/голос, /checkin_now (§6.3–6.4 ТЗ)."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from app.bot.messages import UNKNOWN_USER_TEXT
from app.db.models import DialogStateEnum, TaskStatus
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_dialog_state,
    get_task_by_id,
)
from app.db.session import get_session
from app.bot.dialog_context import DialogContext
from app.db.models import SharedScope
from app.services.checkin import (
    apply_status,
    build_checkin_payload,
    load_checkin_tasks,
    on_stuck_status,
    send_checkin,
)
from app.services.summary import (
    build_summary_texts,
    clear_pending_summary,
    finalize_summary,
    store_pending_summary,
    summary_confirm_prompt,
)
from app.bot.keyboards import kb_summary_send
from app.services.tracking import process_checkin_message
from app.services.voice import (
    EmptyTranscriptionError,
    VOICE_NOTHING_HEARD,
    VOICE_TOO_LONG,
    VOICE_TRANSCRIBE_FAILED,
    detect_audio_source,
    duration_ok,
    message_has_audio,
    transcribe_message_audio,
)

router = Router(name="checkin")

_CALLBACK_RE = re.compile(r"^t:(\d+):(done|in_progress|stuck)$")
_SUMMARY_SEND_RE = re.compile(r"^sm:yn:(yes|no)$")


def parse_checkin_callback(data: str) -> tuple[int, TaskStatus] | None:
    match = _CALLBACK_RE.match(data)
    if not match:
        return None
    status = TaskStatus(match.group(2))
    return int(match.group(1)), status


class InCheckin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.text and message.text.startswith("/"):
            return False
        if not message.text and not message_has_audio(message):
            return False
        async with get_session() as session:
            member = await get_member_by_chat_id(session, message.chat.id)
            if member is None:
                return False
            dialog = await get_or_create_dialog_state(session, member.id)
            return dialog.state == DialogStateEnum.checkin


@router.message(Command("checkin_now"))
async def cmd_checkin_now(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return

    sent = await send_checkin(message.bot, member)
    if not sent:
        await message.answer("Не удалось отправить чек-ин — напиши ведущему.")


@router.callback_query(F.data.regexp(r"^t:\d+:(done|in_progress|stuck)$"))
async def cb_checkin_status(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    parsed = parse_checkin_callback(callback.data)
    if parsed is None:
        await callback.answer()
        return
    task_id, new_status = parsed

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return

        task = await get_task_by_id(session, task_id)
        if task is None or task.member_id != member.id:
            await callback.answer("Задача не найдена.", show_alert=True)
            return

        if task.status == new_status:
            await callback.answer("Уже отмечено")
            return

        updated = await apply_status(session, task_id, new_status)
        if updated is None:
            await callback.answer("Не удалось обновить статус.", show_alert=True)
            return

        _, tasks = await load_checkin_tasks(session, member)

    text, markup = build_checkin_payload(tasks)
    await callback.answer("Записал")
    await callback.message.edit_text(text, reply_markup=markup)

    if new_status == TaskStatus.stuck:
        await on_stuck_status(callback.bot, callback.message.chat.id, updated)


@router.message(InCheckin())
async def handle_checkin_freeform(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return

        user_text: str | None = message.text
        if message_has_audio(message):
            source = detect_audio_source(message)
            duration = source[2] if source else None
            if not duration_ok(duration):
                await message.answer(VOICE_TOO_LONG)
                return
            try:
                user_text = await transcribe_message_audio(message.bot, message)
            except EmptyTranscriptionError:
                await message.answer(VOICE_NOTHING_HEARD)
                return
            except Exception:
                await message.answer(VOICE_TRANSCRIBE_FAILED)
                return
            if not user_text:
                await message.answer(VOICE_TRANSCRIBE_FAILED)
                return

        if not user_text:
            return

        week_id, tasks = await load_checkin_tasks(session, member)
        if not tasks:
            await message.answer(
                "На эту неделю задач нет — отметь статусы, когда они появятся."
            )
            return

        try:
            result = await process_checkin_message(session, member, week_id, user_text)
        except RuntimeError:
            await message.answer(
                "Сейчас не могу разобрать ответ через LLM — отметь статусы кнопками."
            )
            return

        _, tasks = await load_checkin_tasks(session, member)
        stuck_tasks = [t for t in tasks if t.id in result.newly_stuck_task_ids]

    await message.answer(result.reply_text)

    if result.report_ready and result.raw_llm:
        parsed = build_summary_texts(member, tasks, result.raw_llm)
        async with get_session() as session:
            await store_pending_summary(
                session,
                member.id,
                week_id=week_id,
                member_text=parsed.member_text,
                facilitator_text=parsed.facilitator_text,
            )
        confirm = summary_confirm_prompt(member.visibility)
        await message.answer(
            f"{parsed.member_text}\n\n{confirm}",
            reply_markup=kb_summary_send(),
        )
    elif result.report_ready:
        await message.answer(
            "Похоже, итог готов — но не смог собрать сводку. "
            "Напиши ведущему, если нужно зафиксировать вручную."
        )

    if stuck_tasks:
        for task in stuck_tasks:
            await on_stuck_status(message.bot, message.chat.id, task)

    if tasks and not result.report_ready:
        text, markup = build_checkin_payload(tasks)
        await message.answer(text, reply_markup=markup)


def _after_send_message(scope: SharedScope, *, accepted: bool) -> str:
    if not accepted:
        return "Ок, итог сохранён только у тебя — никуда не отправлял."
    if scope == SharedScope.group:
        return "Готово — итог ушёл в общую витрину для группы."
    if scope == SharedScope.facilitator:
        return "Готово — отправил ведущему."
    if scope == SharedScope.private:
        return "Сохранил итог только для тебя — по твоим настройкам видимости."
    return "Итог сохранён."


@router.callback_query(F.data.regexp(r"^sm:yn:(yes|no)$"))
async def cb_summary_send(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    match = _SUMMARY_SEND_RE.match(callback.data)
    if match is None:
        await callback.answer()
        return
    send = match.group(1) == "yes"

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return

        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        if not ctx.has_pending_summary():
            await callback.answer("Сводка уже обработана или устарела.", show_alert=True)
            return

        week_id = ctx.pending_summary_week_id
        member_text = ctx.pending_summary_member_text or ""
        facilitator_text = ctx.pending_summary_facilitator_text or ""
        assert week_id is not None

        scope = await finalize_summary(
            session,
            callback.bot,
            member,
            week_id=week_id,
            member_text=member_text,
            facilitator_text=facilitator_text,
            send=send,
        )
        await clear_pending_summary(session, member.id)

    await callback.answer("Готово")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(_after_send_message(scope, accepted=send))

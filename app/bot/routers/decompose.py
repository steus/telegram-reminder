"""Декомпозиция задачи по согласию (§6.4 ТЗ)."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.bot.dialog_context import DialogContext
from app.bot.keyboards import kb_decompose_confirm
from app.bot.messages import UNKNOWN_USER_TEXT
from app.db.models import DialogStateEnum
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    get_task_by_id,
    set_dialog_state,
    update_dialog_context,
)
from app.db.session import get_session
from app.services.decompose import (
    DECOMPOSE_DECLINED,
    confirm_decomposed_steps,
    continue_decompose_dialog,
    start_decompose_flow,
)
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

router = Router(name="decompose")

_DECOMPOSE_OFFER_RE = re.compile(r"^dc:yn:(yes|no):(\d+)$")
_DECOMPOSE_OK_RE = re.compile(r"^dc:ok:(\d+)$")
_DECOMPOSE_ED_RE = re.compile(r"^dc:ed:(\d+)$")


class InDecomposing(BaseFilter):
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
            return dialog.state == DialogStateEnum.decomposing


@router.callback_query(F.data.regexp(_DECOMPOSE_OFFER_RE))
async def cb_decompose_offer(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    match = _DECOMPOSE_OFFER_RE.match(callback.data)
    if match is None:
        await callback.answer()
        return
    accept = match.group(1) == "yes"
    task_id = int(match.group(2))

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return

        task = await get_task_by_id(session, task_id)
        if task is None or task.member_id != member.id:
            await callback.answer("Задача не найдена.", show_alert=True)
            return

        if not accept:
            await set_dialog_state(session, member.id, DialogStateEnum.checkin)
            reply = DECOMPOSE_DECLINED
            markup = None
        else:
            reply = await start_decompose_flow(session, member, task)
            markup = kb_decompose_confirm(task_id)

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(reply, reply_markup=markup)


@router.callback_query(F.data.regexp(_DECOMPOSE_OK_RE))
async def cb_decompose_confirm(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    match = _DECOMPOSE_OK_RE.match(callback.data)
    if match is None:
        await callback.answer()
        return
    task_id = int(match.group(1))

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return

        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        if ctx.decompose_task_id != task_id:
            await callback.answer("Шаги уже изменились — попробуй ещё раз.", show_alert=True)
            return

        week = await get_or_create_current_week(session, member.group_id)
        reply, _ = await confirm_decomposed_steps(session, member, week)

    await callback.answer("Зафиксировал!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(reply)


@router.callback_query(F.data.regexp(_DECOMPOSE_ED_RE))
async def cb_decompose_edit(callback: CallbackQuery) -> None:
    if callback.message is None:
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Пришли исправленный список шагов — каждый с новой строки."
    )


@router.message(InDecomposing())
async def handle_decompose_input(message: Message) -> None:
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

        reply = await continue_decompose_dialog(session, member, user_text)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        markup = (
            kb_decompose_confirm(ctx.decompose_task_id)
            if ctx.decompose_steps and ctx.decompose_task_id
            else None
        )

    await message.answer(reply, reply_markup=markup)

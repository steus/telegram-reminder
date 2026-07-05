"""Профиль участника: JTBD-анкета, просмотр, заполнение (§8A)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from app.bot.command_names import CMD_MY_PROFILE, CMD_MY_PROFILE_FILL
from app.bot.keyboards import kb_profile_refill_confirm, kb_profile_start
from app.bot.messages import UNKNOWN_USER_TEXT
from app.db.models import DialogStateEnum, OnboardingStatus
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_dialog_state,
    get_or_create_profile,
    reset_profile_for_refill,
)
from app.db.session import get_session
from app.services.profile_onboarding import (
    format_profile_display,
    is_pause_request,
    pause_survey,
    process_survey_message,
    start_survey,
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

router = Router(name="profile")


class InOnboardingSurvey(BaseFilter):
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
            return dialog.state == DialogStateEnum.onboarding_survey


@router.message(Command(CMD_MY_PROFILE))
async def cmd_my_profile(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        profile = await get_or_create_profile(session, member.id)
        if profile.status != OnboardingStatus.completed or not profile.profile_json.strip():
            await message.answer(
                "Профиль ещё не заполнен. Запустить анкету — /my_profile_fill"
            )
            return
        text = format_profile_display(profile.profile_json)

    await message.answer(text)


@router.message(Command(CMD_MY_PROFILE_FILL))
async def cmd_my_profile_fill(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        profile = await get_or_create_profile(session, member.id)

        if profile.status == OnboardingStatus.completed:
            await message.answer(
                "Профиль уже заполнен. Обновить — начнём интервью заново "
                "(старые данные сохранятся до подтверждения нового профиля).",
                reply_markup=kb_profile_refill_confirm(),
            )
            return

        resume = profile.status == OnboardingStatus.in_progress
        try:
            reply = await start_survey(session, member, resume=resume)
        except Exception:
            await message.answer(
                "Сейчас не могу запустить анкету — проверь настройки LLM и попробуй позже."
            )
            return

    await message.answer(reply)


@router.callback_query(F.data == "pf:start")
async def cb_profile_start(callback: CallbackQuery) -> None:
    if callback.message is None:
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        profile = await get_or_create_profile(session, member.id)
        resume = profile.status == OnboardingStatus.in_progress
        if profile.status == OnboardingStatus.completed:
            await reset_profile_for_refill(session, member.id)
            resume = False
        try:
            reply = await start_survey(session, member, resume=resume)
        except Exception:
            await callback.answer("LLM недоступен.", show_alert=True)
            return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(reply)


@router.callback_query(F.data == "pf:later")
async def cb_profile_later(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Ок, без спешки. Анкету можно заполнить позже — /my_profile_fill."
    )


@router.callback_query(F.data == "pf:refill:yes")
async def cb_profile_refill_yes(callback: CallbackQuery) -> None:
    if callback.message is None:
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await reset_profile_for_refill(session, member.id)
        try:
            reply = await start_survey(session, member, resume=False)
        except Exception:
            await callback.answer("LLM недоступен.", show_alert=True)
            return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(reply)


@router.callback_query(F.data == "pf:refill:no")
async def cb_profile_refill_no(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Ок, оставляем текущий профиль.")


@router.message(InOnboardingSurvey())
async def handle_survey_message(message: Message) -> None:
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

        if is_pause_request(user_text):
            reply = await pause_survey(session, member.id)
            await message.answer(reply)
            return

        try:
            result = await process_survey_message(session, member, user_text)
        except Exception:
            await message.answer(
                "Сейчас не могу обработать ответ — попробуй чуть позже."
            )
            return

    await message.answer(result.reply_text)

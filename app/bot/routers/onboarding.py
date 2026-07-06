"""Онбординг: /start, кнопочная настройка участника (§6.1 ТЗ)."""

from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.dialog_context import DialogContext
from app.bot.fsm_sync import sync_fsm_from_context
from app.bot.onboarding_flow import (
    onboarding_prompt,
    parse_checkin_time,
    parse_email,
    parse_phone,
    parse_time_callback_data,
)
from app.bot.states import OnboardingStates
from app.db.models import DialogStateEnum, InputMode, Visibility
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_dialog_state,
    set_dialog_state,
    update_dialog_context,
    update_member_settings,
)
from app.db.session import get_session

from app.bot.messages import CUSTOM_TIME_TEXT, UNKNOWN_USER_TEXT

router = Router(name="onboarding")


async def _send_step(message: Message, step: str) -> None:
    text, keyboard = onboarding_prompt(step)
    if keyboard is None:
        await message.answer(text)
        return
    await message.answer(text, reply_markup=keyboard)


async def _finish_onboarding(message: Message, member_id: int, name: str) -> None:
    async with get_session() as session:
        await set_dialog_state(session, member_id, DialogStateEnum.idle)
    await message.answer(
        f"Готово, {name}! Настройки сохранены — буду рядом, когда понадоблюсь.\n\n"
        "Если захочешь что-то поменять — /settings.\n"
        "Справка по командам — /help."
    )


async def _proceed_after_onboarding_step(
    message: Message,
    state: FSMContext,
    *,
    member_id: int,
    name: str,
    ctx: DialogContext,
) -> None:
    if ctx.onboarded:
        await _finish_onboarding(message, member_id, name)
        await state.clear()
        return

    await sync_fsm_from_context(state, ctx)
    text, keyboard = onboarding_prompt(ctx.step or "ping")
    if keyboard is None:
        await message.answer(text)
        return
    await message.answer(text, reply_markup=keyboard)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            await state.clear()
            return

        if not member.is_active:
            await message.answer(
                "Твоя запись пока неактивна. Если это ошибка — напиши ведущему."
            )
            await state.clear()
            return

        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)

        if ctx.onboarded:
            await message.answer(
                f"С возвращением, {member.full_name}! "
                "Настройки можно поменять в /settings.\n"
                "Справка по командам — /help."
            )
            await state.clear()
            return

        if ctx.step is None:
            ctx.start_onboarding()
            await update_dialog_context(session, member.id, ctx.to_json())

        step = ctx.step or "input_mode"

    await sync_fsm_from_context(state, ctx)
    await _send_step(message, step)


@router.callback_query(F.data.startswith("ob:im:"))
async def cb_onboarding_input_mode(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    mode_value = callback.data.rsplit(":", 1)[-1]
    mode = InputMode(mode_value)

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await update_member_settings(session, member, input_mode=mode)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    await callback.answer()
    if ctx.onboarded:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _finish_onboarding(callback.message, member_id, name)
        await state.clear()
        return

    await sync_fsm_from_context(state, ctx)
    text, keyboard = onboarding_prompt(ctx.step or "visibility")
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("ob:vis:"))
async def cb_onboarding_visibility(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    vis_value = callback.data.rsplit(":", 1)[-1]
    visibility = Visibility(vis_value)

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await update_member_settings(session, member, visibility=visibility)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    await callback.answer()
    if ctx.onboarded:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _finish_onboarding(callback.message, member_id, name)
        await state.clear()
        return

    await sync_fsm_from_context(state, ctx)
    text, keyboard = onboarding_prompt(ctx.step or "weekday")
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.message(OnboardingStates.email, F.text)
async def msg_onboarding_email(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    email = parse_email(message.text)
    if email is None:
        await message.answer(
            "Не похоже на email. Попробуй ещё раз, например: name@example.com"
        )
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        await update_member_settings(session, member, email=email)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    await _proceed_after_onboarding_step(
        message, state, member_id=member_id, name=name, ctx=ctx
    )


@router.message(OnboardingStates.phone, F.text)
async def msg_onboarding_phone(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    phone = parse_phone(message.text)
    if phone is None:
        await message.answer(
            "Не получилось разобрать номер. Попробуй ещё раз, например: +372 51234567 или 51234567"
        )
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        await update_member_settings(session, member, phone=phone)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    await _proceed_after_onboarding_step(
        message, state, member_id=member_id, name=name, ctx=ctx
    )


@router.callback_query(F.data.startswith("ob:wd:"))
async def cb_onboarding_weekday(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    weekday = int(callback.data.rsplit(":", 1)[-1])

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await update_member_settings(session, member, checkin_weekday=weekday)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    await callback.answer()
    if ctx.onboarded:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _finish_onboarding(callback.message, member_id, name)
        await state.clear()
        return

    await sync_fsm_from_context(state, ctx)
    text, keyboard = onboarding_prompt(ctx.step or "time")
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "ob:tm:custom")
async def cb_onboarding_time_custom(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.set_state(OnboardingStates.custom_time)
    await callback.answer()
    await callback.message.edit_text(CUSTOM_TIME_TEXT)


@router.callback_query(F.data.startswith("ob:tm:") & ~F.data.endswith(":custom"))
async def cb_onboarding_time(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    parsed = parse_time_callback_data(callback.data, "ob:tm")
    if parsed is None:
        await callback.answer("Не получилось разобрать время.", show_alert=True)
        return
    await _save_onboarding_time(callback, state, parsed)


@router.message(OnboardingStates.custom_time, F.text)
async def msg_onboarding_custom_time(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    parsed = parse_checkin_time(message.text)
    if parsed is None:
        await message.answer("Не получилось разобрать время. Попробуй формат ЧЧ:ММ.")
        return
    await _save_onboarding_time_message(message, state, parsed)


async def _save_onboarding_time(
    callback: CallbackQuery, state: FSMContext, checkin_time: time
) -> None:
    if callback.message is None:
        return
    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await update_member_settings(session, member, checkin_time=checkin_time)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    await callback.answer()
    if ctx.onboarded:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _finish_onboarding(callback.message, member_id, name)
        await state.clear()
        return

    await sync_fsm_from_context(state, ctx)
    text, keyboard = onboarding_prompt(ctx.step or "ping")
    await callback.message.edit_text(text, reply_markup=keyboard)


async def _save_onboarding_time_message(
    message: Message, state: FSMContext, checkin_time: time
) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        await update_member_settings(session, member, checkin_time=checkin_time)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        name = member.full_name
        member_id = member.id
        if ctx.onboarded:
            await set_dialog_state(session, member_id, DialogStateEnum.idle)

    if ctx.onboarded:
        await _finish_onboarding(message, member_id, name)
        await state.clear()
        return

    await sync_fsm_from_context(state, ctx)
    await _send_step(message, ctx.step or "ping")


@router.callback_query(F.data.startswith("ob:ping:"))
async def cb_onboarding_ping(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    ping = callback.data.rsplit(":", 1)[-1] == "1"

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await update_member_settings(session, member, midweek_ping=ping)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.advance_onboarding()
        await update_dialog_context(session, member.id, ctx.to_json())
        await set_dialog_state(session, member.id, DialogStateEnum.idle)
        name = member.full_name
        member_id = member.id

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _finish_onboarding(callback.message, member_id, name)
    await state.clear()

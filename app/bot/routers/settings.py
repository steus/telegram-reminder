"""Настройки участника: /settings (§6 ТЗ)."""

from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.dialog_context import DialogContext
from app.bot.fsm_sync import sync_fsm_from_context
from app.bot import keyboards as kb
from app.bot.onboarding_flow import parse_checkin_time, settings_edit_prompt
from app.bot.messages import CUSTOM_TIME_TEXT, UNKNOWN_USER_TEXT
from app.bot.states import SettingsStates
from app.db.models import InputMode, Visibility
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_dialog_state,
    update_dialog_context,
    update_member_settings,
)
from app.db.session import get_session

router = Router(name="settings")


async def _show_settings_menu(message: Message, member_id: int) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        summary = kb.format_member_settings(member)
    await message.answer(
        f"Твои настройки:\n\n{summary}\n\nЧто хочешь изменить?",
        reply_markup=kb.kb_settings_menu(),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            await state.clear()
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        if not ctx.onboarded:
            await message.answer(
                "Сначала давай закончим знакомство — нажми /start и пройди пару шагов."
            )
            return
        ctx.clear_settings_edit()
        await update_dialog_context(session, member.id, ctx.to_json())

    await state.set_state(SettingsStates.menu)
    await _show_settings_menu(message, member.id)


@router.callback_query(F.data == "st:menu")
async def cb_settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.clear_settings_edit()
        await update_dialog_context(session, member.id, ctx.to_json())
        summary = kb.format_member_settings(member)

    await callback.answer()
    await state.set_state(SettingsStates.menu)
    await callback.message.edit_text(
        f"Твои настройки:\n\n{summary}\n\nЧто хочешь изменить?",
        reply_markup=kb.kb_settings_menu(),
    )


@router.callback_query(F.data.startswith("st:ed:"))
async def cb_settings_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    field = callback.data.rsplit(":", 1)[-1]

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.begin_settings_edit(field)
        await update_dialog_context(session, member.id, ctx.to_json())

    await sync_fsm_from_context(state, ctx)
    text, keyboard = settings_edit_prompt(field)
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("st:im:"))
async def cb_settings_input_mode(callback: CallbackQuery, state: FSMContext) -> None:
    await _apply_settings_choice(callback, state, input_mode=InputMode(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("st:vis:"))
async def cb_settings_visibility(callback: CallbackQuery, state: FSMContext) -> None:
    await _apply_settings_choice(
        callback, state, visibility=Visibility(callback.data.rsplit(":", 1)[-1])
    )


@router.callback_query(F.data.startswith("st:wd:"))
async def cb_settings_weekday(callback: CallbackQuery, state: FSMContext) -> None:
    await _apply_settings_choice(
        callback, state, checkin_weekday=int(callback.data.rsplit(":", 1)[-1])
    )


@router.callback_query(F.data == "st:tm:custom")
async def cb_settings_time_custom(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.set_state(SettingsStates.custom_time)
    await callback.answer()
    await callback.message.edit_text(CUSTOM_TIME_TEXT)


@router.callback_query(F.data.startswith("st:tm:") & ~F.data.endswith(":custom"))
async def cb_settings_time(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None:
        return
    time_str = callback.data.rsplit(":", 1)[-1]
    hour, minute = map(int, time_str.split(":"))
    await _apply_settings_choice(callback, state, checkin_time=time(hour, minute))


@router.callback_query(F.data.startswith("st:ping:"))
async def cb_settings_ping(callback: CallbackQuery, state: FSMContext) -> None:
    ping = callback.data.rsplit(":", 1)[-1] == "1"  # type: ignore[union-attr]
    await _apply_settings_choice(callback, state, midweek_ping=ping)


@router.message(SettingsStates.custom_time, F.text)
async def msg_settings_custom_time(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    parsed = parse_checkin_time(message.text)
    if parsed is None:
        await message.answer("Не получилось разобрать время. Попробуй формат ЧЧ:ММ.")
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        await update_member_settings(session, member, checkin_time=parsed)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.clear_settings_edit()
        await update_dialog_context(session, member.id, ctx.to_json())
        summary = kb.format_member_settings(member)

    await state.set_state(SettingsStates.menu)
    await message.answer(
        f"Время обновлено.\n\n{summary}",
        reply_markup=kb.kb_settings_menu(),
    )


async def _apply_settings_choice(callback: CallbackQuery, state: FSMContext, **fields) -> None:
    if callback.message is None:
        return
    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await update_member_settings(session, member, **fields)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.clear_settings_edit()
        await update_dialog_context(session, member.id, ctx.to_json())
        summary = kb.format_member_settings(member)

    await callback.answer("Сохранено")
    await state.set_state(SettingsStates.menu)
    await callback.message.edit_text(
        f"Готово!\n\n{summary}\n\nЧто ещё изменить?",
        reply_markup=kb.kb_settings_menu(),
    )

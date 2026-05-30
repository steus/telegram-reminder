"""Команды ведущего: plaud_url и ручная вставка транскрипта (§10 ТЗ)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.dialog_context import DialogContext
from app.bot.states import FacilitatorStates
from app.db.repo import (
    get_group_by_facilitator_chat_id,
    get_member_by_chat_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    update_dialog_context,
    update_week_plaud_url,
    update_week_transcript,
)
from app.db.session import get_session
from app.services.auto_goal_setup import (
    AutoExtractionResult,
    format_facilitator_report,
    run_auto_extraction_for_group,
    should_confirm_resend,
)
from app.services.plaud_action_plan import count_action_plan_sections, has_action_plan_markers

router = Router(name="facilitator")
logger = logging.getLogger(__name__)

# Одним сообщением — one-shot; длиннее — только через /paste_done.
_ONE_SHOT_MAX_LEN = 3500


def _not_facilitator_text(chat_id: int) -> str:
    return (
        "Эта команда доступна только ведущему группы.\n"
        f"Твой chat_id в этом чате: {chat_id}\n"
        "Добавь его в таблицу group_facilitator (или через seed "
        "--facilitator-chat-id)."
    )


def _kb_confirm_resend(week_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Разослать участникам",
                    callback_data=f"fc:send:{week_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💾 Только сохранить",
                    callback_data="fc:save",
                )
            ],
        ]
    )


async def _facilitator_group(chat_id: int):
    async with get_session() as session:
        return await get_group_by_facilitator_chat_id(session, chat_id)


async def _load_paste_context(
    chat_id: int, state: FSMContext
) -> tuple[int | None, str, DialogContext | None, int | None]:
    """(group_id, pending_text, dialog_ctx, member_id)."""
    data = await state.get_data()
    group_id = data.get("facilitator_group_id")
    pending = (data.get("pending_transcript") or "").strip()

    async with get_session() as session:
        member = await get_member_by_chat_id(session, chat_id)
        ctx: DialogContext | None = None
        if member is not None:
            dialog = await get_or_create_dialog_state(session, member.id)
            ctx = DialogContext.from_json(dialog.context_json)
            if ctx.is_facilitator_pasting():
                group_id = ctx.facilitator_group_id or group_id
                if ctx.facilitator_pending:
                    pending = ctx.facilitator_pending.strip()

    return group_id, pending, ctx, member.id if member else None


async def _save_paste_context(
    chat_id: int,
    state: FSMContext,
    *,
    group_id: int,
    pending: str,
    ctx: DialogContext | None,
    member_id: int | None,
) -> None:
    await state.set_state(FacilitatorStates.pasting_transcript)
    await state.update_data(facilitator_group_id=group_id, pending_transcript=pending)
    if ctx is not None and member_id is not None:
        ctx.facilitator_group_id = group_id
        ctx.facilitator_pending = pending
        async with get_session() as session:
            await update_dialog_context(session, member_id, ctx.to_json())


async def _clear_paste_context(
    chat_id: int, state: FSMContext, ctx: DialogContext | None, member_id: int | None
) -> None:
    await state.clear()
    if ctx is not None and member_id is not None:
        ctx.clear_facilitator_paste()
        async with get_session() as session:
            await update_dialog_context(session, member_id, ctx.to_json())


async def _finalize_transcript(
    message: Message,
    state: FSMContext,
    *,
    group_id: int,
    text: str,
    ctx: DialogContext | None = None,
    member_id: int | None = None,
) -> None:
    text = text.strip()
    if len(text) < 20:
        await message.answer(
            "Текст слишком короткий. Пришли блок «План действий» с @-заголовками."
        )
        return

    if not has_action_plan_markers(text):
        await message.answer(
            "В тексте нет @-заголовков (например @Степан). "
            "Пришли блок «План действий» целиком или добавь части и /paste_done."
        )
        return

    try:
        async with get_session() as session:
            week = await get_or_create_current_week(session, group_id)
            had_transcript = bool(week.transcript_text and week.transcript_text.strip())
            await update_week_transcript(session, week.id, text)
            week_id = week.id

            if await should_confirm_resend(
                session, group_id, week_id, had_transcript=had_transcript
            ):
                await state.set_state(FacilitatorStates.confirm_resend)
                await state.update_data(facilitator_group_id=group_id, resend_week_id=week_id)
                if ctx is not None and member_id is not None:
                    ctx.facilitator_group_id = group_id
                    ctx.facilitator_pending = text
                    await update_dialog_context(session, member_id, ctx.to_json())
                await message.answer(
                    "Транскрипт обновлён. Участникам уже отправляли задачи на подтверждение.\n\n"
                    "Разослать заново с учётом правок?",
                    reply_markup=_kb_confirm_resend(week_id),
                )
                return

            result = await run_auto_extraction_for_group(
                session, message.bot, group_id
            )
    except Exception as exc:
        logger.exception("Failed to finalize transcript paste")
        err = str(exc).lower()
        if "locked" in err or "database is locked" in err:
            await message.answer(
                "Не удалось сохранить: база SQLite занята (database is locked).\n\n"
                "Закрой DB Browser или другие программы с файлом data/app.db, "
                "затем отправь блок @Степан ещё раз."
            )
        else:
            await message.answer(
                "Не удалось обработать транскрипт — внутренняя ошибка. "
                "Попробуй ещё раз или напиши разработчику."
            )
        return

    await _clear_paste_context(message.chat.id, state, ctx, member_id)
    await message.answer(format_facilitator_report(result))


class FacilitatorText(BaseFilter):
    """Текст от ведущего (не команда)."""

    async def __call__(self, message: Message) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        group = await _facilitator_group(message.chat.id)
        return group is not None


@router.message(Command("set_plaud_url"))
async def cmd_set_plaud_url(message: Message, command: CommandObject) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    url = (command.args or "").strip()
    if not url:
        await message.answer("Укажи ссылку: /set_plaud_url https://...")
        return

    async with get_session() as session:
        week = await get_or_create_current_week(session, group.id)
        await update_week_plaud_url(session, week.id, url)
        week_label = week.start_date.strftime("%d.%m.%Y")

    await message.answer(f"Ссылка на транскрипт сохранена для недели с {week_label}.")


@router.message(Command("paste_transcript", "paste_transacipt"))
async def cmd_paste_transcript(message: Message, state: FSMContext) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    ctx: DialogContext | None = None
    member_id: int | None = None
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is not None:
            member_id = member.id
            dialog = await get_or_create_dialog_state(session, member.id)
            ctx = DialogContext.from_json(dialog.context_json)
            ctx.start_facilitator_paste(group.id)
            await update_dialog_context(session, member.id, ctx.to_json())

    await _save_paste_context(
        message.chat.id, state, group_id=group.id, pending="", ctx=ctx, member_id=member_id
    )
    await message.answer(
        "Жду текст. Можно так:\n\n"
        "1) Весь «План действий» одним сообщением → сразу обработаю.\n"
        "2) Несколькими частями (@Speaker 1, потом @Степан …) → в конце /paste_done.\n"
        "3) Только свою секцию (@Степан …) без /paste_transcript — тоже сработает."
    )


@router.message(Command("paste_done"))
async def cmd_paste_done(message: Message, state: FSMContext) -> None:
    group_id, pending, ctx, member_id = await _load_paste_context(message.chat.id, state)
    if group_id is None or not pending:
        await message.answer(
            "Нет накопленного текста. Сначала /paste_transcript и пришли части плана."
        )
        return
    await _finalize_transcript(
        message, state, group_id=group_id, text=pending, ctx=ctx, member_id=member_id
    )


@router.message(FacilitatorText())
async def handle_facilitator_transcript_text(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith("SettingsStates:"):
        return

    group = await _facilitator_group(message.chat.id)
    if group is None:
        return

    chunk = (message.text or "").strip()
    if len(chunk) < 10:
        await message.answer("Слишком короткий фрагмент.")
        return

    group_id, pending, ctx, member_id = await _load_paste_context(message.chat.id, state)
    in_paste_mode = group_id is not None

    # One-shot: одна секция @… без предварительной команды
    if not in_paste_mode and has_action_plan_markers(chunk) and len(chunk) <= _ONE_SHOT_MAX_LEN:
        await _finalize_transcript(
            message,
            state,
            group_id=group.id,
            text=chunk,
            ctx=ctx,
            member_id=member_id,
        )
        return

    if not in_paste_mode:
        await message.answer(
            "Чтобы вставить транскрипт, сначала /paste_transcript "
            "или пришли одним сообщением блок с @-заголовками."
        )
        return

    combined = f"{pending}\n\n{chunk}".strip() if pending else chunk

    if ctx is None:
        async with get_session() as session:
            member = await get_member_by_chat_id(session, message.chat.id)
            if member is not None:
                member_id = member.id
                dialog = await get_or_create_dialog_state(session, member.id)
                ctx = DialogContext.from_json(dialog.context_json)
                ctx.facilitator_group_id = group_id
                ctx.facilitator_pending = combined
                await update_dialog_context(session, member.id, ctx.to_json())
    elif member_id is not None:
        ctx.facilitator_pending = combined
        async with get_session() as session:
            await update_dialog_context(session, member_id, ctx.to_json())

    await _save_paste_context(
        message.chat.id,
        state,
        group_id=group_id or group.id,
        pending=combined,
        ctx=ctx,
        member_id=member_id,
    )

    # После /paste_transcript: одна @-секция — ждём остальные; несколько — полный план одним сообщением
    if not pending and count_action_plan_sections(combined) >= 2:
        await _finalize_transcript(
            message,
            state,
            group_id=group_id or group.id,
            text=combined,
            ctx=ctx,
            member_id=member_id,
        )
        return

    await message.answer(
        f"Принял ({len(combined)} символов). "
        "Пришли следующие @-секции, затем /paste_done."
    )


@router.callback_query(F.data.startswith("fc:send:"))
async def cb_facilitator_resend_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return

    data = await state.get_data()
    group_id = data.get("facilitator_group_id")
    if group_id is None:
        await callback.answer("Сессия истекла — начни с /paste_transcript", show_alert=True)
        return

    async with get_session() as session:
        result = await run_auto_extraction_for_group(
            session, callback.bot, group_id, force=True
        )

    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_facilitator_report(result))


@router.callback_query(F.data == "fc:save")
async def cb_facilitator_resend_no(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return

    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_facilitator_report(AutoExtractionResult(), saved_only=True))

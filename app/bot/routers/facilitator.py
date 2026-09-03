"""Команды ведущего: plaud_url и ручная вставка транскрипта (§10 ТЗ)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import keyboards as kb
from app.bot.command_names import (
    CMD_GROUP,
    CMD_GROUP_PASTE_DONE,
    CMD_GROUP_PASTE_TRANSCRIPT,
    CMD_GROUP_SET_PLAUD,
    CMD_GROUP_SYNC_GOALS,
    CMD_GROUP_VIEW_GOALS,
    CMD_GOALS,
)
from app.bot.routers.membership import (
    send_group_invite,
    send_group_members,
    send_group_requests,
)
from app.services.sheet_sync import sync_group_goals_to_sheet
from app.bot.dialog_context import DialogContext
from app.bot.facilitator_priority import facilitator_paste_takes_priority
from app.bot.states import FacilitatorStates
from app.bot.task_confirmation import (
    confirmation_message,
    format_task_list,
    kb_task_confirmation,
)
from app.db.models import DialogStateEnum, TaskSource
from app.db.repo import (
    get_group_by_facilitator_chat_id,
    get_member_by_chat_id,
    get_member_by_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    list_active_members_for_group,
    list_tasks_for_member_week,
    replace_tasks,
    update_dialog_context,
    update_week_plaud_url,
    update_week_transcript,
)
from app.services.group_goals_view import build_group_goals_report
from app.db.session import get_session
from app.services.auto_goal_setup import (
    AutoExtractionResult,
    assign_plan_section_to_member,
    format_facilitator_report,
    preview_paste_assignments,
    run_auto_extraction_for_group,
    should_confirm_resend,
)
from app.services.extraction import start_auto_goal_confirmation, structure_goals
from app.services.plaud_action_plan import (
    count_action_plan_sections,
    extract_tasks_from_action_plan,
    has_action_plan_markers,
    list_unmatched_action_plan_headers,
    merge_action_plan_transcripts,
    replace_member_action_plan_tasks,
)

router = Router(name="facilitator")
logger = logging.getLogger(__name__)

# Одним сообщением — one-shot; длиннее — только через /paste_done.
_ONE_SHOT_MAX_LEN = 3500


_GROUP_MENU_TEXT = "Меню ведущего — выбери раздел:"
_GROUP_MEMBERS_TEXT = "Участники и заявки:"
_GROUP_GOALS_TEXT = "Задачи группы:"
_GROUP_TRANSCRIPT_TEXT = "Транскрипт (Plaud):"


def _not_facilitator_text(chat_id: int) -> str:
    return (
        "Эта команда доступна только ведущему группы.\n"
        f"Твой chat_id в этом чате: {chat_id}\n"
        "Добавь его в таблицу group_facilitator (или через seed "
        "--facilitator-chat-id)."
    )


def _kb_confirm_send(week_id: int) -> InlineKeyboardMarkup:
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
                    text="✏️ Править задачи",
                    callback_data=f"fc:ed:pick:{week_id}",
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
            "Текст слишком короткий. Пришли блок с @-заголовками "
            "(например @Имя и список задач)."
        )
        return

    if not has_action_plan_markers(text):
        await message.answer(
            "В тексте нет @-заголовков (например @Имя на отдельной строке). "
            "Пришли секции целиком или добавь части и /paste_done."
        )
        return

    try:
        async with get_session() as session:
            week = await get_or_create_current_week(session, group_id)
            had_transcript = bool(week.transcript_text and week.transcript_text.strip())
            merged = merge_action_plan_transcripts(week.transcript_text, text)
            await update_week_transcript(session, week.id, merged)
            week.transcript_text = merged
            week_id = week.id

            preview = await preview_paste_assignments(session, group_id, text)
            resend = await should_confirm_resend(
                session,
                group_id,
                week_id,
                had_transcript=had_transcript,
                pasted_text=text,
            )
            if ctx is not None and member_id is not None:
                ctx.facilitator_group_id = group_id
                ctx.facilitator_pending = text
                await update_dialog_context(session, member_id, ctx.to_json())
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

    await state.set_state(FacilitatorStates.confirm_resend)
    await state.update_data(
        facilitator_group_id=group_id,
        resend_week_id=week_id,
        pending_transcript=text,
    )
    await message.answer(
        format_facilitator_report(preview, preview=True, resend=resend),
        reply_markup=_kb_confirm_send(week_id),
    )


async def _send_extraction_report(
    message: Message,
    state: FSMContext,
    *,
    group_id: int,
    result: AutoExtractionResult,
) -> None:
    text = format_facilitator_report(result)
    if not result.unmatched_headers:
        await message.answer(text)
        return

    # Список секций не держим в FSM (MemoryStorage легко сбрасывается) —
    # при клике пересчитываем из week.transcript_text.
    await state.set_state(FacilitatorStates.assigning_section)
    await state.update_data(facilitator_group_id=group_id)
    await message.answer(
        text,
        reply_markup=kb.kb_assign_unmatched_headers(result.unmatched_headers),
    )


async def _unmatched_headers_for_chat(chat_id: int) -> tuple[int | None, list[str]]:
    """(group_id, несматченные @-заголовки из текущего транскрипта)."""
    group = await _facilitator_group(chat_id)
    if group is None:
        return None, []
    async with get_session() as session:
        week = await get_or_create_current_week(session, group.id)
        members = await list_active_members_for_group(session, group.id)
        headers = list_unmatched_action_plan_headers(
            week.transcript_text or "",
            [m.full_name for m in members],
        )
    return group.id, headers


class FacilitatorText(BaseFilter):
    """Текст от ведущего (не команда), если не в другом диалоге участника."""

    async def __call__(self, message: Message) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        group = await _facilitator_group(message.chat.id)
        if group is None:
            return False
        text = message.text
        # Ведущий часто совпадает с участником: не перехватывать чек-ин, цели, декомпозицию, анкету.
        async with get_session() as session:
            member = await get_member_by_chat_id(session, message.chat.id)
            if member is not None:
                dialog = await get_or_create_dialog_state(session, member.id)
                ctx = DialogContext.from_json(dialog.context_json)
                # Свои задачи (/my_goals_set) важнее незавершённой вставки транскрипта.
                if dialog.state == DialogStateEnum.confirming_tasks and ctx.task_step in (
                    "collect",
                    "correct",
                ):
                    return False
                if dialog.state in (
                    DialogStateEnum.checkin,
                    DialogStateEnum.decomposing,
                ):
                    return False
                # JTBD-анкета: уступаем, кроме paste-режима и @-секций «Плана действий».
                if dialog.state == DialogStateEnum.onboarding_survey:
                    return facilitator_paste_takes_priority(ctx, text)
                # Правка задач участника ведущим — отдельный хендлер.
                if ctx.is_facilitator_editing_goals():
                    return False
                if facilitator_paste_takes_priority(ctx, text):
                    return True
        return True


class FacilitatorEditingGoals(BaseFilter):
    """Ведущий вводит новый список задач для выбранного участника."""

    async def __call__(self, message: Message) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        if await _facilitator_group(message.chat.id) is None:
            return False
        async with get_session() as session:
            member = await get_member_by_chat_id(session, message.chat.id)
            if member is None:
                return False
            dialog = await get_or_create_dialog_state(session, member.id)
            ctx = DialogContext.from_json(dialog.context_json)
            return ctx.is_facilitator_editing_goals()


async def send_group_sync_goals(message: Message, group) -> None:
    async with get_session() as session:
        result = await sync_group_goals_to_sheet(session, group)
    await message.answer(result.message)


async def send_group_view_goals(message: Message, group) -> None:
    async with get_session() as session:
        week = await get_or_create_current_week(session, group.id)
        report = await build_group_goals_report(session, group, week)
    await message.answer(report)


async def _show_group_menu(message: Message) -> None:
    await message.answer(_GROUP_MENU_TEXT, reply_markup=kb.kb_group_menu())


@router.message(Command(CMD_GROUP))
async def cmd_group_menu(message: Message) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return
    await _show_group_menu(message)


@router.callback_query(F.data == "fc:m:root")
async def cb_group_menu_root(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(_GROUP_MENU_TEXT, reply_markup=kb.kb_group_menu())


@router.callback_query(F.data == "fc:m:members")
async def cb_group_menu_members(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        _GROUP_MEMBERS_TEXT, reply_markup=kb.kb_group_members_submenu()
    )


@router.callback_query(F.data == "fc:m:goals")
async def cb_group_menu_goals(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        _GROUP_GOALS_TEXT, reply_markup=kb.kb_group_goals_submenu()
    )


@router.callback_query(F.data == "fc:m:transcript")
async def cb_group_menu_transcript(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        _GROUP_TRANSCRIPT_TEXT, reply_markup=kb.kb_group_transcript_submenu()
    )


@router.callback_query(F.data == "fc:act:invite")
async def cb_group_act_invite(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await send_group_invite(callback.message, group)


@router.callback_query(F.data == "fc:act:members")
async def cb_group_act_members(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await send_group_members(callback.message, group)


@router.callback_query(F.data == "fc:act:requests")
async def cb_group_act_requests(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await send_group_requests(callback.message, group)


@router.callback_query(F.data == "fc:act:goals_view")
async def cb_group_act_goals_view(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await send_group_view_goals(callback.message, group)


@router.callback_query(F.data == "fc:act:goals_edit")
async def cb_group_act_goals_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    async with get_session() as session:
        members = await list_active_members_for_group(session, group.id)
    if not members:
        await callback.answer("Нет активных участников.", show_alert=True)
        return
    await state.update_data(
        facilitator_group_id=group.id,
        edit_return="menu",
        pending_transcript=None,
    )
    await callback.answer()
    await callback.message.answer(
        "Чьи задачи правим?",
        reply_markup=kb.kb_pick_member_for_edit(members, back_callback="fc:m:goals"),
    )


@router.callback_query(F.data == "fc:act:goals_sync")
async def cb_group_act_goals_sync(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await send_group_sync_goals(callback.message, group)


@router.callback_query(F.data == "fc:act:plaud")
async def cb_group_act_plaud(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        f"Сохранить ссылку на Plaud:\n/{CMD_GROUP_SET_PLAUD} https://..."
    )


async def _begin_paste_transcript(message: Message, state: FSMContext):
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return None

    ctx: DialogContext | None = None
    member_id: int | None = None
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is not None:
            member_id = member.id
            dialog = await get_or_create_dialog_state(session, member.id)
            ctx = DialogContext.from_json(dialog.context_json)
            ctx.clear_task_flow()
            ctx.start_facilitator_paste(group.id)
            await update_dialog_context(session, member.id, ctx.to_json())

    await _save_paste_context(
        message.chat.id, state, group_id=group.id, pending="", ctx=ctx, member_id=member_id
    )
    return group


async def _show_paste_prompt(message: Message) -> None:
    await message.answer(
        "Жду текст «Плана действий». Можно так:\n\n"
        "1) Одна или несколько @-секций одним сообщением → покажу превью, "
        "разошлю участникам только после твоей кнопки.\n"
        "2) По частям: каждая @-секция сразу в превью "
        f"(или накопи и заверши /{CMD_GROUP_PASTE_DONE}).\n"
        f"3) Без /{CMD_GROUP_PASTE_TRANSCRIPT} — одна @-секция тоже сработает "
        f"(если не вводишь свои задачи через /{CMD_GOALS}).\n\n"
        "Пиши @Имя Фамилия (с пробелом) — иначе Telegram может подставить "
        "чужой публичный @username."
    )


@router.callback_query(F.data == "fc:act:paste")
async def cb_group_act_paste(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    group = await _begin_paste_transcript(callback.message, state)
    if group is None:
        await callback.answer()
        return
    await callback.answer()
    await _show_paste_prompt(callback.message)


@router.callback_query(F.data == "fc:act:paste_done")
async def cb_group_act_paste_done(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    group_id, pending, ctx, member_id = await _load_paste_context(callback.message.chat.id, state)
    if group_id is None or not pending:
        await callback.message.answer(
            f"Нет накопленного текста. Сначала вставь части плана, затем «Завершить вставку» "
            f"или /{CMD_GROUP_PASTE_DONE}."
        )
        return
    await _finalize_transcript(
        callback.message, state, group_id=group_id, text=pending, ctx=ctx, member_id=member_id
    )


@router.message(Command(CMD_GROUP_SYNC_GOALS))
async def cmd_group_sync_goals(message: Message) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    await send_group_sync_goals(message, group)


@router.message(Command(CMD_GROUP_VIEW_GOALS))
async def cmd_group_view_goals(message: Message) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    await send_group_view_goals(message, group)


@router.message(Command(CMD_GROUP_SET_PLAUD))
async def cmd_set_plaud_url(message: Message, command: CommandObject) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    url = (command.args or "").strip()
    if not url:
        await message.answer(f"Укажи ссылку: /{CMD_GROUP_SET_PLAUD} https://...")
        return

    async with get_session() as session:
        week = await get_or_create_current_week(session, group.id)
        await update_week_plaud_url(session, week.id, url)
        week_label = week.start_date.strftime("%d.%m.%Y")

    await message.answer(f"Ссылка на транскрипт сохранена для недели с {week_label}.")


async def _process_paste_chunk(
    message: Message,
    state: FSMContext,
    *,
    group,
    chunk: str,
    finalize_single_section: bool = False,
) -> None:
    chunk = chunk.strip()
    if len(chunk) < 10:
        await message.answer("Слишком короткий фрагмент.")
        return

    group_id, pending, ctx, member_id = await _load_paste_context(message.chat.id, state)
    in_paste_mode = group_id is not None

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
            f"Это похоже на транскрипт встречи. Для группы — /{CMD_GROUP_PASTE_TRANSCRIPT} "
            "или один блок с несколькими @-заголовками.\n\n"
            f"Для своих задач — /{CMD_GOALS} и список строк (без @)."
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

    section_count = count_action_plan_sections(combined)
    # Любая полная @-секция (одна или несколько) — сразу в обработку,
    # чтобы ведущий видел отчёт с задачами, а не «Принял… жди /paste_done».
    if section_count >= 1:
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
        f"Принял ({len(combined)} символов), но @-секций пока не видно.\n"
        f"Пришли блок вида «@Имя» и список задач, либо /{CMD_GROUP_PASTE_DONE}."
    )


@router.message(Command(CMD_GROUP_PASTE_TRANSCRIPT))
async def cmd_paste_transcript(
    message: Message, state: FSMContext, command: CommandObject
) -> None:
    group = await _begin_paste_transcript(message, state)
    if group is None:
        return

    attached = (command.args or "").strip()
    if attached:
        await _process_paste_chunk(
            message,
            state,
            group=group,
            chunk=attached,
            finalize_single_section=True,
        )
        return

    await _show_paste_prompt(message)


@router.message(Command(CMD_GROUP_PASTE_DONE))
async def cmd_paste_done(message: Message, state: FSMContext) -> None:
    group_id, pending, ctx, member_id = await _load_paste_context(message.chat.id, state)
    if group_id is None or not pending:
        await message.answer(
            f"Нет накопленного текста. Сначала /{CMD_GROUP_PASTE_TRANSCRIPT} "
            f"и пришли части плана, затем /{CMD_GROUP_PASTE_DONE}.\n\n"
            f"Либо одним сообщением: /{CMD_GROUP_PASTE_TRANSCRIPT} и сразу текст с @-заголовком, "
            f"или просто блок @Имя без команды."
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

    await _process_paste_chunk(
        message,
        state,
        group=group,
        chunk=message.text or "",
    )


@router.callback_query(F.data.startswith("fc:send:"))
async def cb_facilitator_resend_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return

    data = await state.get_data()
    group_id = data.get("facilitator_group_id")
    if group_id is None:
        await callback.answer(
            f"Сессия истекла — начни с /{CMD_GROUP_PASTE_TRANSCRIPT}", show_alert=True
        )
        return

    pasted = (data.get("pending_transcript") or "").strip()
    ctx: DialogContext | None = None
    member_id: int | None = None

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is not None:
            member_id = member.id
            dialog = await get_or_create_dialog_state(session, member.id)
            ctx = DialogContext.from_json(dialog.context_json)
            if not pasted and ctx.facilitator_pending:
                pasted = ctx.facilitator_pending.strip()

        result = await run_auto_extraction_for_group(
            session,
            callback.bot,
            group_id,
            force=True,
            pasted_text=pasted or None,
        )
        if ctx is not None and member_id is not None:
            ctx.clear_facilitator_paste()
            await update_dialog_context(session, member_id, ctx.to_json())

    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _send_extraction_report(
        callback.message, state, group_id=group_id, result=result
    )


@router.callback_query(F.data == "fc:save")
async def cb_facilitator_resend_no(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is not None:
            dialog = await get_or_create_dialog_state(session, member.id)
            ctx = DialogContext.from_json(dialog.context_json)
            ctx.clear_facilitator_paste()
            await update_dialog_context(session, member.id, ctx.to_json())

    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_facilitator_report(AutoExtractionResult(), saved_only=True))


_FACILITATOR_EDIT_PROMPT = (
    "Пришли исправленный список задач — каждая с новой строки.\n"
    "Я обновлю список и покажу снова."
)


async def _begin_edit_member_goals(
    message: Message,
    state: FSMContext,
    *,
    group_id: int,
    target_member_id: int,
    edit_return: str,
) -> None:
    data = await state.get_data()
    pending = (data.get("pending_transcript") or "").strip()

    async with get_session() as session:
        target = await get_member_by_id(session, target_member_id)
        if target is None or not target.is_active or target.group_id != group_id:
            await message.answer("Участник не найден или неактивен.")
            return
        week = await get_or_create_current_week(session, group_id)
        db_tasks = await list_tasks_for_member_week(session, target.id, week.id)
        plan_source = pending or (week.transcript_text or "")
        plan_tasks = extract_tasks_from_action_plan(plan_source, target.full_name) or []
        facilitator = await get_member_by_chat_id(session, message.chat.id)
        if facilitator is not None:
            dialog = await get_or_create_dialog_state(session, facilitator.id)
            ctx = DialogContext.from_json(dialog.context_json)
            ctx.start_facilitator_edit(target.id)
            if edit_return == "preview" and ctx.facilitator_group_id is None:
                ctx.facilitator_group_id = group_id
            await update_dialog_context(session, facilitator.id, ctx.to_json())

        target_name = target.full_name
        week_label = week.start_date.strftime("%d.%m.%Y")
        week_id = week.id
        if db_tasks:
            current = format_task_list(db_tasks)
        elif plan_tasks:
            current = "\n".join(f"{i}. {t}" for i, t in enumerate(plan_tasks, start=1))
        else:
            current = "Задач пока нет."

    await state.set_state(FacilitatorStates.editing_member_goals)
    await state.update_data(
        facilitator_group_id=group_id,
        edit_member_id=target_member_id,
        edit_return=edit_return,
        pending_transcript=data.get("pending_transcript"),
        resend_week_id=data.get("resend_week_id") or week_id,
    )

    await message.answer(
        f"Задачи {target_name} (неделя с {week_label}):\n\n"
        f"{current}\n\n{_FACILITATOR_EDIT_PROMPT}"
    )


async def _reshow_paste_preview(message: Message, state: FSMContext, *, group_id: int) -> None:
    data = await state.get_data()
    pasted = (data.get("pending_transcript") or "").strip()
    week_id = data.get("resend_week_id")
    async with get_session() as session:
        week = await get_or_create_current_week(session, group_id)
        if not pasted:
            pasted = (week.transcript_text or "").strip()
        if week_id is None:
            week_id = week.id
        preview = await preview_paste_assignments(session, group_id, pasted)
        resend = await should_confirm_resend(
            session,
            group_id,
            week.id,
            had_transcript=True,
            pasted_text=pasted,
        )
    await state.set_state(FacilitatorStates.confirm_resend)
    await state.update_data(
        facilitator_group_id=group_id,
        resend_week_id=week_id,
        pending_transcript=pasted,
        edit_member_id=None,
    )
    await message.answer(
        format_facilitator_report(preview, preview=True, resend=resend),
        reply_markup=_kb_confirm_send(week_id),
    )


@router.callback_query(F.data.startswith("fc:ed:pick:"))
async def cb_edit_pick_from_preview(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    data = await state.get_data()
    pasted = (data.get("pending_transcript") or "").strip()
    async with get_session() as session:
        members = await list_active_members_for_group(session, group.id)
        if pasted:
            preview = await preview_paste_assignments(session, group.id, pasted)
            matched_names = set(preview.sent_with_goals) | {
                name for name, _ in preview.without_goals
            }
            if matched_names:
                members = [m for m in members if m.full_name in matched_names] or members
    if not members:
        await callback.answer("Нет участников для правки.", show_alert=True)
        return
    await state.update_data(edit_return="preview", facilitator_group_id=group.id)
    await callback.answer()
    await callback.message.answer(
        "Чьи задачи из превью правим?",
        reply_markup=kb.kb_pick_member_for_edit(
            members, back_callback=f"fc:ed:back:{group.id}"
        ),
    )


@router.callback_query(F.data.startswith("fc:ed:back:"))
async def cb_edit_back_to_preview(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    try:
        group_id = int(callback.data.removeprefix("fc:ed:back:"))
    except ValueError:
        await callback.answer("Сессия устарела.", show_alert=True)
        return
    if await _facilitator_group(callback.message.chat.id) is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await _reshow_paste_preview(callback.message, state, group_id=group_id)


@router.callback_query(F.data.startswith("fc:ed:m:"))
async def cb_edit_pick_member(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    try:
        target_id = int(callback.data.removeprefix("fc:ed:m:"))
    except ValueError:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return
    data = await state.get_data()
    edit_return = data.get("edit_return") or "menu"
    await callback.answer()
    await _begin_edit_member_goals(
        callback.message,
        state,
        group_id=group.id,
        target_member_id=target_id,
        edit_return=edit_return,
    )


@router.message(FacilitatorEditingGoals())
async def handle_facilitator_edit_goals_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data.get("facilitator_group_id")
    target_id = data.get("edit_member_id")
    edit_return = data.get("edit_return") or "menu"
    if group_id is None or target_id is None:
        await message.answer("Сессия правки истекла — выбери участника снова.")
        await state.clear()
        return

    await message.answer(
        "Принял — сохраняю список, обычно несколько секунд. Подожди подтверждение."
    )

    texts = await structure_goals(message.text or "")
    if not texts:
        await message.answer(
            "Не нашёл ни одной задачи. Пришли списком — каждая с новой строки."
        )
        return

    async with get_session() as session:
        target = await get_member_by_id(session, target_id)
        if target is None or target.group_id != group_id:
            await message.answer("Участник не найден.")
            return
        week = await get_or_create_current_week(session, group_id)
        await replace_tasks(
            session,
            member_id=target.id,
            week_id=week.id,
            texts=texts,
            source=TaskSource.manual,
        )
        new_transcript = replace_member_action_plan_tasks(
            week.transcript_text or "",
            member_name=target.full_name,
            tasks=texts,
        )
        await update_week_transcript(session, week.id, new_transcript)
        week.transcript_text = new_transcript

        pending = (data.get("pending_transcript") or "").strip()
        if pending:
            pending = replace_member_action_plan_tasks(
                pending, member_name=target.full_name, tasks=texts
            )
        elif edit_return == "preview":
            pending = replace_member_action_plan_tasks(
                "", member_name=target.full_name, tasks=texts
            )

        facilitator = await get_member_by_chat_id(session, message.chat.id)
        if facilitator is not None:
            dialog = await get_or_create_dialog_state(session, facilitator.id)
            ctx = DialogContext.from_json(dialog.context_json)
            ctx.clear_facilitator_edit()
            if pending:
                ctx.facilitator_pending = pending
                ctx.facilitator_group_id = group_id
            await update_dialog_context(session, facilitator.id, ctx.to_json())

        tasks = await list_tasks_for_member_week(session, target.id, week.id)
        name = target.full_name
        week_id = week.id

    await state.update_data(
        pending_transcript=pending or None,
        edit_member_id=None,
        resend_week_id=week_id,
    )

    body = format_task_list(tasks)
    if edit_return == "preview":
        await message.answer(f"Обновил задачи для {name}:\n\n{body}")
        await _reshow_paste_preview(message, state, group_id=group_id)
        return

    await state.clear()
    await message.answer(
        f"Сохранил задачи для {name}:\n\n{body}",
        reply_markup=kb.kb_after_facilitator_edit(target_id),
    )


@router.callback_query(F.data.startswith("fc:ed:send:"))
async def cb_edit_send_to_member(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    try:
        target_id = int(callback.data.removeprefix("fc:ed:send:"))
    except ValueError:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    async with get_session() as session:
        target = await get_member_by_id(session, target_id)
        if target is None or not target.is_active or target.group_id != group.id:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        week = await get_or_create_current_week(session, group.id)
        tasks = await list_tasks_for_member_week(session, target.id, week.id)
        if not tasks:
            await callback.answer("У участника нет задач на эту неделю.", show_alert=True)
            return
        await start_auto_goal_confirmation(session, target)
        dialog = await get_or_create_dialog_state(session, target.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.show_task_confirmation()
        await update_dialog_context(session, target.id, ctx.to_json())
        await callback.bot.send_message(
            target.telegram_chat_id,
            confirmation_message(tasks),
            reply_markup=kb_task_confirmation(week.id),
        )
        name = target.full_name

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Экран подтверждения отправлен: {name}.")
    await state.clear()


@router.callback_query(F.data == "fc:ed:done")
async def cb_edit_done(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Ок, задачи сохранены без рассылки.")


@router.callback_query(F.data == "fc:asg:x")
async def cb_assign_skip(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Ок, без ручного назначения.")


@router.callback_query(F.data == "fc:asg:back")
async def cb_assign_back_to_headers(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    group_id, headers = await _unmatched_headers_for_chat(callback.message.chat.id)
    if group_id is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    if not headers:
        await state.clear()
        await callback.answer()
        await callback.message.edit_text("Несопоставленных секций больше нет.")
        return
    await state.set_state(FacilitatorStates.assigning_section)
    await state.update_data(facilitator_group_id=group_id)
    await callback.answer()
    await callback.message.edit_text(
        "Кому назначить несопоставленные секции?",
        reply_markup=kb.kb_assign_unmatched_headers(headers),
    )


@router.callback_query(F.data.startswith("fc:asg:h:"))
async def cb_assign_pick_header(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    group_id, headers = await _unmatched_headers_for_chat(callback.message.chat.id)
    if group_id is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    try:
        idx = int(callback.data.removeprefix("fc:asg:h:"))
        header = headers[idx]
    except (ValueError, IndexError):
        await callback.answer(
            "Список обновился — открой секции снова из отчёта или вставь план.",
            show_alert=True,
        )
        return

    async with get_session() as session:
        members = await list_active_members_for_group(session, group_id)

    if not members:
        await callback.answer("В группе нет активных участников.", show_alert=True)
        return

    await state.set_state(FacilitatorStates.assigning_section)
    await state.update_data(facilitator_group_id=group_id)
    await callback.answer()
    await callback.message.edit_text(
        f"Кому назначить задачи из @{header}?",
        reply_markup=kb.kb_assign_pick_member(members, header_idx=idx),
    )


@router.callback_query(F.data.startswith("fc:asg:p:"))
async def cb_assign_to_member(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    group_id, headers = await _unmatched_headers_for_chat(callback.message.chat.id)
    if group_id is None:
        await callback.answer("Нет прав.", show_alert=True)
        return
    parts = callback.data.removeprefix("fc:asg:p:").split(":")
    if len(parts) != 2:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return
    try:
        header_idx = int(parts[0])
        member_id = int(parts[1])
        header = headers[header_idx]
    except (ValueError, IndexError):
        await callback.answer(
            "Список обновился — вернись к @-секциям и выбери снова.",
            show_alert=True,
        )
        return

    async with get_session() as session:
        ok, detail = await assign_plan_section_to_member(
            session,
            callback.bot,
            group_id=group_id,
            member_id=member_id,
            header=header,
        )
        remaining: list[str] = []
        if ok:
            members = await list_active_members_for_group(session, group_id)
            week = await get_or_create_current_week(session, group_id)
            remaining = list_unmatched_action_plan_headers(
                week.transcript_text or "",
                [m.full_name for m in members],
            )

    await callback.answer()
    if not ok:
        await callback.message.answer(f"Не вышло: {detail}")
        return

    if remaining:
        await state.set_state(FacilitatorStates.assigning_section)
        await state.update_data(facilitator_group_id=group_id)
        await callback.message.edit_text(
            f"Готово: @{header} → {detail}.\n\nОстались несопоставленные:",
            reply_markup=kb.kb_assign_unmatched_headers(remaining),
        )
    else:
        await state.clear()
        await callback.message.edit_text(
            f"Готово: @{header} → {detail}.\nВсе секции разобраны."
        )

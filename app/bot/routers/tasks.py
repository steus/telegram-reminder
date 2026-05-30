"""Задачи: private-ввод, подтверждение, /tasks (§6.2, §6.6 ТЗ)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.dialog_context import DialogContext
from app.bot.messages import UNKNOWN_USER_TEXT
from app.bot.states import TaskStates
from app.bot.task_confirmation import (
    confirmation_message,
    format_task_list,
    kb_task_confirmation,
)
from app.db.models import DialogStateEnum, InputMode
from app.db.repo import (
    get_member_by_chat_id,
    get_or_create_current_week,
    get_or_create_dialog_state,
    list_tasks_for_member_week,
    replace_tasks,
    set_dialog_state,
    set_tasks_confirmed,
    update_dialog_context,
)
from app.db.session import get_session
from app.services.extraction import (
    CORRECTION_PROMPT,
    GOAL_COLLECTION_PROMPT,
    start_private_goal_collection,
    structure_goals,
)

router = Router(name="tasks")


class InTaskInput(BaseFilter):
    """Сообщение в режиме ввода/правки задач (collect или correct)."""

    async def __call__(self, message: Message) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        async with get_session() as session:
            member = await get_member_by_chat_id(session, message.chat.id)
            if member is None:
                return False
            dialog = await get_or_create_dialog_state(session, member.id)
            if dialog.state != DialogStateEnum.confirming_tasks:
                return False
            ctx = DialogContext.from_json(dialog.context_json)
            return ctx.task_step in ("collect", "correct")


async def _show_confirmation(message: Message, member_id: int, week_id: int) -> None:
    async with get_session() as session:
        tasks = await list_tasks_for_member_week(session, member_id, week_id)
    await message.answer(
        confirmation_message(tasks),
        reply_markup=kb_task_confirmation(week_id),
    )


@router.message(Command("setgoals"))
async def cmd_setgoals(message: Message, state: FSMContext) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        if not ctx.onboarded:
            await message.answer("Сначала давай закончим знакомство — нажми /start.")
            return
        if member.input_mode != InputMode.private:
            await message.answer(
                "У тебя включён автоматический режим — задачи подтянутся из транскрипта "
                "после встречи. Если хочешь вводить приватно — смени в /settings."
            )
            return

        await start_private_goal_collection(session, member)
        ctx.start_task_collection()
        await update_dialog_context(session, member.id, ctx.to_json())

    await state.set_state(TaskStates.collecting)
    await message.answer(GOAL_COLLECTION_PROMPT)


@router.message(Command("tasks"))
async def cmd_tasks(message: Message) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            await message.answer(UNKNOWN_USER_TEXT)
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        if not ctx.onboarded:
            await message.answer("Сначала давай закончим знакомство — нажми /start.")
            return

        week = await get_or_create_current_week(session, member.group_id)
        tasks = await list_tasks_for_member_week(session, member.id, week.id)

    if not tasks:
        await message.answer(
            "Задач на эту неделю пока нет. "
            "Чтобы добавить — /setgoals (пока вручную, позже — по расписанию)."
        )
        return

    await message.answer(
        f"Твои задачи на неделю с {week.start_date.strftime('%d.%m.%Y')}:\n\n"
        f"{format_task_list(tasks, show_status=True)}"
    )


@router.message(InTaskInput(), F.text)
async def handle_goal_text(message: Message, state: FSMContext) -> None:
    async with get_session() as session:
        member = await get_member_by_chat_id(session, message.chat.id)
        if member is None:
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        week_id = dialog.active_week_id
        if week_id is None:
            week_id = await start_private_goal_collection(session, member)
            dialog.active_week_id = week_id

        texts = await structure_goals(message.text or "")
        if not texts:
            await message.answer(
                "Не нашёл ни одной задачи. Попробуй списком — каждая цель с новой строки."
            )
            return

        await replace_tasks(
            session,
            member_id=member.id,
            week_id=week_id,
            texts=texts,
        )
        ctx.show_task_confirmation()
        await update_dialog_context(session, member.id, ctx.to_json())
        member_id = member.id

    await state.set_state(TaskStates.confirming)
    await _show_confirmation(message, member_id, week_id)


@router.callback_query(F.data.startswith("tk:ok:"))
async def cb_tasks_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    week_id = int(callback.data.rsplit(":", 1)[-1])

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        await set_tasks_confirmed(session, member.id, week_id, confirmed=True)
        await set_dialog_state(session, member.id, DialogStateEnum.idle)
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.clear_task_flow()
        await update_dialog_context(session, member.id, ctx.to_json())

    await callback.answer("Зафиксировал!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Отлично, задачи на неделю зафиксированы. Держу их в фокусе вместе с тобой."
    )
    await state.clear()


@router.callback_query(F.data.startswith("tk:ed:"))
async def cb_tasks_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return

    async with get_session() as session:
        member = await get_member_by_chat_id(session, callback.message.chat.id)
        if member is None:
            await callback.answer("Не нашёл тебя в группе.", show_alert=True)
            return
        dialog = await get_or_create_dialog_state(session, member.id)
        ctx = DialogContext.from_json(dialog.context_json)
        ctx.start_task_correction()
        await update_dialog_context(session, member.id, ctx.to_json())

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(TaskStates.correcting)
    await callback.message.answer(CORRECTION_PROMPT)

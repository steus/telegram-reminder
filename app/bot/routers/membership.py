"""Вступление в группу, заявки и управление участниками."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.command_names import (
    CMD_GROUP_INVITE,
    CMD_GROUP_MEMBERS,
    CMD_GROUP_REQUESTS,
)
from app.bot.commands import register_facilitator_commands_for_chat
from app.bot.keyboards import (
    kb_group_members,
    kb_member_delete_confirm,
    kb_membership_join_confirm,
    kb_membership_request_decision,
)
from app.bot.messages import (
    MEMBERSHIP_APPROVED_TEXT,
    MEMBERSHIP_ASK_NAME_TEXT,
    MEMBERSHIP_INVALID_NAME_TEXT,
    MEMBERSHIP_PENDING_TEXT,
    MEMBERSHIP_REJECTED_TEXT,
    MEMBERSHIP_REQUEST_SENT_TEXT,
    UNKNOWN_USER_TEXT,
)
from app.bot.states import MembershipStates
from app.config import settings
from app.db.models import MembershipRequestStatus
from app.db.repo import (
    add_group_facilitator,
    approve_membership_request,
    create_membership_request,
    deactivate_member,
    delete_member,
    get_group,
    get_group_by_facilitator_chat_id,
    get_group_by_invite_code,
    get_member_by_chat_id,
    get_member_by_id,
    get_membership_request_by_id,
    get_pending_membership_request_by_chat,
    is_group_facilitator,
    list_group_facilitator_chat_ids,
    list_members_for_group,
    list_pending_membership_requests_for_group,
    reject_membership_request,
)
from app.db.session import get_session
from app.services.membership import (
    build_invite_link,
    format_facilitator_request_message,
    format_members_list,
    normalize_member_name,
    parse_start_invite_code,
    validate_member_name_latin,
)

router = Router(name="membership")
logger = logging.getLogger(__name__)


class UnknownTelegramUser(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        async with get_session() as session:
            member = await get_member_by_chat_id(session, message.chat.id)
        return member is None


def _not_facilitator_text(chat_id: int) -> str:
    return (
        "Эта команда доступна только ведущему группы.\n"
        f"Твой chat_id в этом чате: {chat_id}"
    )


async def _facilitator_group(chat_id: int):
    async with get_session() as session:
        return await get_group_by_facilitator_chat_id(session, chat_id)


async def _notify_facilitators_new_request(
    bot: Bot, *, group_id: int, request_id: int
) -> None:
    async with get_session() as session:
        request = await get_membership_request_by_id(session, request_id)
        if request is None:
            return
        group = await get_group(session, group_id)
        if group is None:
            logger.error("Group %s not found for membership request %s", group_id, request_id)
            return
        facilitator_ids = await list_group_facilitator_chat_ids(session, group_id)
        text = format_facilitator_request_message(
            full_name=request.full_name,
            group_name=group.name,
            telegram_username=request.telegram_username,
            chat_id=request.telegram_chat_id,
        )
        keyboard = kb_membership_request_decision(request_id)

    for chat_id in facilitator_ids:
        try:
            await bot.send_message(int(chat_id), text, reply_markup=keyboard)
        except Exception:
            logger.exception(
                "Failed to notify facilitator %s about request %s", chat_id, request_id
            )


async def _send_pending_requests(message: Message, group_id: int) -> None:
    async with get_session() as session:
        group = await get_group(session, group_id)
        group_name = group.name if group else "?"
        pending = await list_pending_membership_requests_for_group(session, group_id)
        items = [
            (
                req.id,
                req.full_name,
                group_name,
                req.telegram_username,
                req.telegram_chat_id,
            )
            for req in pending
        ]

    if not items:
        await message.answer("Ожидающих заявок нет.")
        return

    for request_id, full_name, group_name, username, chat_id in items:
        text = format_facilitator_request_message(
            full_name=full_name,
            group_name=group_name,
            telegram_username=username,
            chat_id=chat_id,
        )
        await message.answer(text, reply_markup=kb_membership_request_decision(request_id))


@router.message(CommandStart(), UnknownTelegramUser())
async def cmd_start_unknown(
    message: Message, state: FSMContext, command: CommandObject
) -> None:
    async with get_session() as session:
        pending = await get_pending_membership_request_by_chat(session, message.chat.id)
        if pending is not None:
            await message.answer(MEMBERSHIP_PENDING_TEXT)
            await state.clear()
            return

    invite_code = parse_start_invite_code(command.args)
    if invite_code is None:
        await message.answer(UNKNOWN_USER_TEXT)
        await state.clear()
        return

    async with get_session() as session:
        group = await get_group_by_invite_code(session, invite_code)
        if group is None:
            await message.answer(
                "Ссылка-приглашение не сработала — возможно, она устарела. "
                "Попроси у ведущего новую через /group_invite."
            )
            await state.clear()
            return

    await message.answer(
        f"Группа «{group.name}». Хочешь подать заявку на вступление?",
        reply_markup=kb_membership_join_confirm(group.id),
    )


@router.callback_query(F.data.startswith("mj:join:yes:"))
async def cb_membership_join_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return

    group_id = int(callback.data.rsplit(":", 1)[-1])
    async with get_session() as session:
        if await get_member_by_chat_id(session, callback.message.chat.id) is not None:
            await callback.answer("Ты уже в группе.", show_alert=True)
            return
        pending = await get_pending_membership_request_by_chat(
            session, callback.message.chat.id
        )
        if pending is not None:
            await callback.answer("Заявка уже отправлена.", show_alert=True)
            return

    await state.set_state(MembershipStates.waiting_name)
    await state.update_data(membership_group_id=group_id)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(MEMBERSHIP_ASK_NAME_TEXT)


@router.callback_query(F.data.startswith("mj:join:no:"))
async def cb_membership_join_no(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Хорошо. Если передумаешь — перейди по ссылке от ведущего снова."
    )


@router.message(MembershipStates.waiting_name, F.text)
async def msg_membership_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        return

    if not validate_member_name_latin(message.text):
        await message.answer(MEMBERSHIP_INVALID_NAME_TEXT)
        return

    data = await state.get_data()
    group_id = data.get("membership_group_id")
    if group_id is None:
        await state.clear()
        await message.answer(UNKNOWN_USER_TEXT)
        return

    full_name = normalize_member_name(message.text)
    username = message.from_user.username if message.from_user else None

    async with get_session() as session:
        if await get_member_by_chat_id(session, message.chat.id) is not None:
            await state.clear()
            await message.answer("Ты уже в группе — нажми /start.")
            return
        pending = await get_pending_membership_request_by_chat(session, message.chat.id)
        if pending is not None:
            await state.clear()
            await message.answer(MEMBERSHIP_PENDING_TEXT)
            return

        request = await create_membership_request(
            session,
            group_id=group_id,
            telegram_chat_id=message.chat.id,
            full_name=full_name,
            telegram_username=username,
        )
        request_id = request.id

    await state.clear()
    await message.answer(MEMBERSHIP_REQUEST_SENT_TEXT)
    await _notify_facilitators_new_request(
        message.bot, group_id=group_id, request_id=request_id
    )


@router.callback_query(F.data.startswith("mj:ok:"))
async def cb_membership_approve(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    request_id = int(callback.data.rsplit(":", 1)[-1])
    async with get_session() as session:
        request = await get_membership_request_by_id(session, request_id)
        if request is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return
        if request.status != MembershipRequestStatus.pending:
            await callback.answer("Заявка уже обработана.", show_alert=True)
            return
        if not await is_group_facilitator(
            session, request.group_id, callback.message.chat.id
        ):
            await callback.answer("Нет прав для этой группы.", show_alert=True)
            return
        if await get_member_by_chat_id(session, request.telegram_chat_id) is not None:
            await reject_membership_request(
                session,
                request,
                resolved_by_chat_id=callback.message.chat.id,
            )
            await callback.answer("Участник уже есть в базе.", show_alert=True)
            return

        await approve_membership_request(
            session,
            request,
            resolved_by_chat_id=callback.message.chat.id,
            timezone=settings.default_timezone,
        )
        applicant_chat_id = int(request.telegram_chat_id)
        approved_name = request.full_name

    await callback.answer("Принято")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Принят(а): {approved_name}.")
    try:
        await callback.bot.send_message(applicant_chat_id, MEMBERSHIP_APPROVED_TEXT)
    except Exception:
        logger.exception("Failed to notify approved member %s", applicant_chat_id)


@router.callback_query(F.data.startswith("mj:no:"))
async def cb_membership_reject(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    request_id = int(callback.data.rsplit(":", 1)[-1])
    async with get_session() as session:
        request = await get_membership_request_by_id(session, request_id)
        if request is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return
        if request.status != MembershipRequestStatus.pending:
            await callback.answer("Заявка уже обработана.", show_alert=True)
            return
        if not await is_group_facilitator(
            session, request.group_id, callback.message.chat.id
        ):
            await callback.answer("Нет прав для этой группы.", show_alert=True)
            return

        await reject_membership_request(
            session,
            request,
            resolved_by_chat_id=callback.message.chat.id,
        )
        applicant_chat_id = int(request.telegram_chat_id)
        full_name = request.full_name

    await callback.answer("Отклонено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Отклонена заявка: {full_name}.")
    try:
        await callback.bot.send_message(applicant_chat_id, MEMBERSHIP_REJECTED_TEXT)
    except Exception:
        logger.exception("Failed to notify rejected applicant %s", applicant_chat_id)


async def send_group_invite(message: Message, group) -> None:
    me = await message.bot.get_me()
    if not me.username:
        await message.answer("У бота нет username — задай его в @BotFather.")
        return

    link = build_invite_link(me.username, group.invite_code)
    await message.answer(
        f"Ссылка-приглашение в «{group.name}»:\n\n{link}\n\n"
        "Передай её новому участнику — он подаст заявку, а ты или другой ведущий "
        "примете решение."
    )


async def send_group_members(message: Message, group) -> None:
    async with get_session() as session:
        members = await list_members_for_group(session, group.id)
        facilitator_ids = set(await list_group_facilitator_chat_ids(session, group.id))

    rows = [
        (m.id, m.full_name, m.telegram_chat_id, m.is_active) for m in members
    ]
    text = format_members_list(members=rows, facilitator_chat_ids=facilitator_ids)
    keyboard = kb_group_members(members, facilitator_ids)
    await message.answer(text, reply_markup=keyboard)


async def send_group_requests(message: Message, group) -> None:
    await _send_pending_requests(message, group.id)


@router.message(Command(CMD_GROUP_INVITE))
async def cmd_group_invite(message: Message) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    await send_group_invite(message, group)


@router.message(Command(CMD_GROUP_MEMBERS))
async def cmd_group_members(message: Message) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    await send_group_members(message, group)


@router.message(Command(CMD_GROUP_REQUESTS))
async def cmd_group_requests(message: Message) -> None:
    group = await _facilitator_group(message.chat.id)
    if group is None:
        await message.answer(_not_facilitator_text(message.chat.id))
        return

    await send_group_requests(message, group)


@router.callback_query(F.data.startswith("mj:fac:"))
async def cb_make_facilitator(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    member_id = int(callback.data.rsplit(":", 1)[-1])
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return

    async with get_session() as session:
        member = await get_member_by_id(session, member_id)
        if member is None or member.group_id != group.id:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        if not member.is_active:
            await callback.answer("Участник неактивен.", show_alert=True)
            return
        added = await add_group_facilitator(session, group.id, member.telegram_chat_id)
        chat_id = int(member.telegram_chat_id)
        member_name = member.full_name

    if added is None:
        await callback.answer("Уже ведущий.", show_alert=True)
        return

    await register_facilitator_commands_for_chat(callback.bot, chat_id)
    await callback.answer("Назначен ведущим")
    await callback.message.answer(
        f"{member_name} теперь ведущий группы «{group.name}»."
    )


@router.callback_query(F.data.startswith("mj:deact:"))
async def cb_deactivate_member(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    member_id = int(callback.data.rsplit(":", 1)[-1])
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return

    async with get_session() as session:
        member = await get_member_by_id(session, member_id)
        if member is None or member.group_id != group.id:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        if str(callback.message.chat.id) == member.telegram_chat_id:
            await callback.answer("Нельзя деактивировать себя.", show_alert=True)
            return
        await deactivate_member(session, member)
        name = member.full_name

    await callback.answer("Деактивирован")
    await callback.message.answer(
        f"{name} деактивирован(а). Чек-ины и задачи для него/неё остановятся."
    )


@router.callback_query(F.data.regexp(r"^mj:del:\d+$"))
async def cb_delete_member_ask(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    member_id = int(callback.data.rsplit(":", 1)[-1])
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return

    async with get_session() as session:
        member = await get_member_by_id(session, member_id)
        if member is None or member.group_id != group.id:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        if str(callback.message.chat.id) == member.telegram_chat_id:
            await callback.answer("Нельзя удалить себя.", show_alert=True)
            return
        name = member.full_name

    await callback.answer()
    await callback.message.answer(
        f"Удалить {name} из группы?\n\n"
        "Запись, задачи и история сводок будут стёрты. "
        "Человек сможет снова подать заявку по invite-ссылке.",
        reply_markup=kb_member_delete_confirm(member_id),
    )


@router.callback_query(F.data.startswith("mj:del:cn:"))
async def cb_delete_member_cancel(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    await callback.answer("Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("mj:del:ok:"))
async def cb_delete_member_confirm(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        return

    member_id = int(callback.data.rsplit(":", 1)[-1])
    group = await _facilitator_group(callback.message.chat.id)
    if group is None:
        await callback.answer("Нет прав.", show_alert=True)
        return

    async with get_session() as session:
        member = await get_member_by_id(session, member_id)
        if member is None or member.group_id != group.id:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        if str(callback.message.chat.id) == member.telegram_chat_id:
            await callback.answer("Нельзя удалить себя.", show_alert=True)
            return
        name = member.full_name
        chat_id = int(member.telegram_chat_id)
        deleted = await delete_member(session, member)

    if not deleted:
        await callback.answer("Нельзя удалить последнего ведущего.", show_alert=True)
        return

    await callback.answer("Удалён")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{name} удалён(а) из группы.")
    try:
        await callback.bot.send_message(
            chat_id,
            "Тебя убрали из группы в боте. Если это ошибка — напиши ведущему.",
        )
    except Exception:
        logger.exception("Failed to notify deleted member %s", chat_id)

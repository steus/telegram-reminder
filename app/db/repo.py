"""Репозиторий — единственная точка доступа к БД для бизнес-логики (§7 ТЗ)."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DialogState,
    DialogStateEnum,
    Group,
    InputMode,
    Member,
    Task,
    TaskSource,
    TaskStatus,
    Visibility,
    Week,
)


async def get_member_by_chat_id(
    session: AsyncSession, chat_id: str | int
) -> Member | None:
    """Найти участника по Telegram chat_id или вернуть None."""
    result = await session.execute(
        select(Member).where(Member.telegram_chat_id == str(chat_id))
    )
    return result.scalar_one_or_none()


async def get_member_by_id(session: AsyncSession, member_id: int) -> Member | None:
    return await session.get(Member, member_id)


async def get_group(session: AsyncSession, group_id: int) -> Group | None:
    return await session.get(Group, group_id)


async def create_group(
    session: AsyncSession,
    *,
    name: str,
    facilitator_chat_id: str,
    sheet_id: str | None = None,
) -> Group:
    group = Group(
        name=name,
        facilitator_chat_id=str(facilitator_chat_id),
        sheet_id=sheet_id,
    )
    session.add(group)
    await session.flush()
    return group


async def create_member(
    session: AsyncSession,
    *,
    group_id: int,
    full_name: str,
    telegram_chat_id: str,
    timezone: str = "Europe/Tallinn",
) -> Member:
    member = Member(
        group_id=group_id,
        full_name=full_name,
        telegram_chat_id=str(telegram_chat_id),
        timezone=timezone,
    )
    session.add(member)
    await session.flush()
    return member


async def update_member(
    session: AsyncSession, member: Member, **fields: Any
) -> Member:
    for key, value in fields.items():
        setattr(member, key, value)
    await session.flush()
    return member


async def get_or_create_dialog_state(
    session: AsyncSession, member_id: int
) -> DialogState:
    dialog = await session.get(DialogState, member_id)
    if dialog is None:
        dialog = DialogState(member_id=member_id, context_json="{}")
        session.add(dialog)
        await session.flush()
    return dialog


async def set_dialog_state(
    session: AsyncSession,
    member_id: int,
    state: DialogStateEnum,
) -> DialogState:
    dialog = await get_or_create_dialog_state(session, member_id)
    dialog.state = state
    await session.flush()
    return dialog


async def update_dialog_context(
    session: AsyncSession,
    member_id: int,
    context_json: str,
) -> DialogState:
    dialog = await get_or_create_dialog_state(session, member_id)
    dialog.context_json = context_json
    await session.flush()
    return dialog


async def update_member_settings(
    session: AsyncSession,
    member: Member,
    *,
    input_mode: InputMode | None = None,
    visibility: Visibility | None = None,
    checkin_weekday: int | None = None,
    checkin_time: time | None = None,
    midweek_ping: bool | None = None,
    timezone: str | None = None,
) -> Member:
    if input_mode is not None:
        member.input_mode = input_mode
    if visibility is not None:
        member.visibility = visibility
    if checkin_weekday is not None:
        member.checkin_weekday = checkin_weekday
    if checkin_time is not None:
        member.checkin_time = checkin_time
    if midweek_ping is not None:
        member.midweek_ping = midweek_ping
    if timezone is not None:
        member.timezone = timezone
    await session.flush()
    return member


async def get_or_create_current_week(
    session: AsyncSession, group_id: int, *, start_date: date | None = None
) -> Week:
    """Текущая (последняя) неделя группы; если нет — создать."""
    result = await session.execute(
        select(Week)
        .where(Week.group_id == group_id)
        .order_by(Week.start_date.desc())
        .limit(1)
    )
    week = result.scalar_one_or_none()
    if week is None:
        week = Week(group_id=group_id, start_date=start_date or date.today())
        session.add(week)
        await session.flush()
    return week


async def list_tasks_for_member_week(
    session: AsyncSession, member_id: int, week_id: int
) -> list[Task]:
    result = await session.execute(
        select(Task)
        .where(Task.member_id == member_id, Task.week_id == week_id)
        .order_by(Task.position)
    )
    return list(result.scalars().all())


async def create_tasks(
    session: AsyncSession,
    *,
    member_id: int,
    week_id: int,
    texts: list[str],
    source: TaskSource = TaskSource.manual,
    confirmed: bool = False,
) -> list[Task]:
    tasks: list[Task] = []
    for idx, text in enumerate(texts):
        task = Task(
            member_id=member_id,
            week_id=week_id,
            text=text,
            source=source,
            position=idx,
            confirmed=confirmed,
            status=TaskStatus.pending,
        )
        session.add(task)
        tasks.append(task)
    await session.flush()
    return tasks


async def replace_tasks(
    session: AsyncSession,
    *,
    member_id: int,
    week_id: int,
    texts: list[str],
    source: TaskSource = TaskSource.manual,
) -> list[Task]:
    await session.execute(
        delete(Task).where(Task.member_id == member_id, Task.week_id == week_id)
    )
    return await create_tasks(
        session,
        member_id=member_id,
        week_id=week_id,
        texts=texts,
        source=source,
        confirmed=False,
    )


async def set_tasks_confirmed(
    session: AsyncSession, member_id: int, week_id: int, *, confirmed: bool = True
) -> None:
    tasks = await list_tasks_for_member_week(session, member_id, week_id)
    for task in tasks:
        task.confirmed = confirmed
    await session.flush()

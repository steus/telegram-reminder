"""Репозиторий — единственная точка доступа к БД для бизнес-логики (§7 ТЗ)."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DialogState,
    DialogStateEnum,
    Group,
    GroupFacilitator,
    InputMode,
    Member,
    SharedScope,
    Summary,
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


async def get_group_by_facilitator_chat_id(
    session: AsyncSession, chat_id: str | int
) -> Group | None:
    """Группа, где chat_id — один из ведущих (group_facilitator)."""
    result = await session.execute(
        select(Group)
        .join(GroupFacilitator, GroupFacilitator.group_id == Group.id)
        .where(GroupFacilitator.telegram_chat_id == str(chat_id))
        .limit(1)
    )
    return result.scalar_one_or_none()


def parse_facilitator_chat_ids(
    *values: str | None, default: str | None = None
) -> list[str]:
    """Разобрать chat_id ведущих: несколько аргументов и/или через запятую."""
    ids: list[str] = []
    for raw in values:
        if not raw:
            continue
        for part in raw.split(","):
            part = part.strip()
            if part and part not in ids:
                ids.append(part)
    if not ids and default:
        return [default]
    return ids


async def list_group_facilitator_chat_ids(
    session: AsyncSession, group_id: int
) -> list[str]:
    result = await session.execute(
        select(GroupFacilitator.telegram_chat_id)
        .where(GroupFacilitator.group_id == group_id)
        .order_by(GroupFacilitator.id)
    )
    return list(result.scalars().all())


async def list_all_facilitator_chat_ids(session: AsyncSession) -> list[int]:
    """Все chat_id ведущих — для меню команд Telegram."""
    result = await session.execute(select(GroupFacilitator.telegram_chat_id))
    return [int(chat_id) for chat_id in result.scalars().all()]


async def add_group_facilitator(
    session: AsyncSession,
    group_id: int,
    telegram_chat_id: str | int,
) -> GroupFacilitator | None:
    """Добавить ведущего группы. None — уже был."""
    chat_id = str(telegram_chat_id)
    result = await session.execute(
        select(GroupFacilitator).where(
            GroupFacilitator.group_id == group_id,
            GroupFacilitator.telegram_chat_id == chat_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return None

    row = GroupFacilitator(group_id=group_id, telegram_chat_id=chat_id)
    session.add(row)
    await session.flush()
    await _sync_group_primary_facilitator(session, group_id)
    return row


async def _sync_group_primary_facilitator(
    session: AsyncSession, group_id: int
) -> None:
    """Денормализация: group.facilitator_chat_id = первый ведущий из списка."""
    group = await session.get(Group, group_id)
    if group is None:
        return
    ids = await list_group_facilitator_chat_ids(session, group_id)
    if ids:
        group.facilitator_chat_id = ids[0]
        await session.flush()


async def create_group(
    session: AsyncSession,
    *,
    name: str,
    facilitator_chat_id: str | None = None,
    facilitator_chat_ids: list[str] | None = None,
    sheet_id: str | None = None,
) -> Group:
    ids = facilitator_chat_ids or (
        [facilitator_chat_id] if facilitator_chat_id else []
    )
    if not ids:
        raise ValueError("At least one facilitator chat_id is required")

    group = Group(
        name=name,
        facilitator_chat_id=str(ids[0]),
        sheet_id=sheet_id,
    )
    session.add(group)
    await session.flush()
    for chat_id in ids:
        session.add(
            GroupFacilitator(group_id=group.id, telegram_chat_id=str(chat_id))
        )
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


async def get_task_by_id(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


async def update_task_status(
    session: AsyncSession, task_id: int, status: TaskStatus
) -> Task | None:
    task = await get_task_by_id(session, task_id)
    if task is None:
        return None
    task.status = status
    await session.flush()
    return task


async def list_active_members(session: AsyncSession) -> list[Member]:
    result = await session.execute(
        select(Member).where(Member.is_active.is_(True)).order_by(Member.id)
    )
    return list(result.scalars().all())


async def list_active_members_for_group(
    session: AsyncSession, group_id: int
) -> list[Member]:
    result = await session.execute(
        select(Member)
        .where(Member.group_id == group_id, Member.is_active.is_(True))
        .order_by(Member.id)
    )
    return list(result.scalars().all())


async def list_auto_members_for_group(
    session: AsyncSession, group_id: int
) -> list[Member]:
    result = await session.execute(
        select(Member).where(
            Member.group_id == group_id,
            Member.is_active.is_(True),
            Member.input_mode == InputMode.auto,
        )
    )
    return list(result.scalars().all())


async def list_group_member_names(
    session: AsyncSession,
    group_id: int,
    *,
    exclude_member_id: int | None = None,
) -> list[str]:
    """Имена активных участников группы (для атрибуции в LLM)."""
    query = (
        select(Member.full_name)
        .where(Member.group_id == group_id, Member.is_active.is_(True))
        .order_by(Member.id)
    )
    if exclude_member_id is not None:
        query = query.where(Member.id != exclude_member_id)
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_week_plaud_url(
    session: AsyncSession, week_id: int, plaud_url: str
) -> Week | None:
    week = await session.get(Week, week_id)
    if week is None:
        return None
    week.plaud_url = plaud_url.strip()
    await session.flush()
    return week


async def update_week_transcript(
    session: AsyncSession, week_id: int, transcript_text: str
) -> Week | None:
    week = await session.get(Week, week_id)
    if week is None:
        return None
    week.transcript_text = transcript_text.strip()
    await session.flush()
    return week


async def get_or_create_next_week(
    session: AsyncSession, group_id: int, after_week: Week
) -> Week:
    """Следующая неделя группы (+7 дней от after_week)."""
    next_start = after_week.start_date + timedelta(days=7)
    result = await session.execute(
        select(Week).where(
            Week.group_id == group_id,
            Week.start_date == next_start,
        )
    )
    week = result.scalar_one_or_none()
    if week is None:
        week = Week(group_id=group_id, start_date=next_start)
        session.add(week)
        await session.flush()
    return week


async def create_summary(
    session: AsyncSession,
    *,
    member_id: int,
    week_id: int,
    member_text: str,
    facilitator_text: str,
    shared_scope: SharedScope,
) -> Summary:
    row = Summary(
        member_id=member_id,
        week_id=week_id,
        member_text=member_text,
        facilitator_text=facilitator_text,
        shared_scope=shared_scope,
    )
    session.add(row)
    await session.flush()
    return row


async def list_summaries_for_member(
    session: AsyncSession, member_id: int
) -> list[Summary]:
    result = await session.execute(
        select(Summary)
        .where(Summary.member_id == member_id)
        .order_by(Summary.created_at.desc())
    )
    return list(result.scalars().all())


async def create_decomposed_subtasks(
    session: AsyncSession,
    *,
    member_id: int,
    parent_task: Task,
    next_week_id: int,
    step_texts: list[str],
) -> list[Task]:
    """Сохранить шаги декомпозиции в следующую неделю; родитель → decomposed."""
    tasks: list[Task] = []
    for idx, text in enumerate(step_texts):
        task = Task(
            member_id=member_id,
            week_id=next_week_id,
            text=text,
            source=TaskSource.decomposed,
            parent_task_id=parent_task.id,
            position=idx,
            confirmed=True,
            status=TaskStatus.pending,
        )
        session.add(task)
        tasks.append(task)
    parent_task.status = TaskStatus.decomposed
    await session.flush()
    return tasks

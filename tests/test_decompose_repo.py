"""Декомпозиция: следующая неделя и подзадачи."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, Group, Member, Task, TaskSource, TaskStatus, Week
from app.db.repo import create_decomposed_subtasks, get_or_create_next_week


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        group = Group(name="G", facilitator_chat_id="1")
        sess.add(group)
        await sess.flush()
        member = Member(
            group_id=group.id,
            full_name="Test",
            telegram_chat_id="100",
        )
        sess.add(member)
        await sess.flush()
        week = Week(group_id=group.id, start_date=date(2026, 5, 26))
        sess.add(week)
        await sess.flush()
        parent = Task(
            member_id=member.id,
            week_id=week.id,
            text="Запустить лендинг",
            source=TaskSource.manual,
            status=TaskStatus.stuck,
            confirmed=True,
        )
        sess.add(parent)
        await sess.commit()
        yield sess

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_create_next_week(session: AsyncSession) -> None:
    week = (await session.execute(select(Week))).scalar_one()
    nxt = await get_or_create_next_week(session, week.group_id, week)
    assert nxt.start_date == date(2026, 6, 2)

    same = await get_or_create_next_week(session, week.group_id, week)
    assert same.id == nxt.id


@pytest.mark.asyncio
async def test_create_decomposed_subtasks(session: AsyncSession) -> None:
    week = (await session.execute(select(Week))).scalar_one()
    parent = (await session.execute(select(Task))).scalar_one()
    nxt = await get_or_create_next_week(session, week.group_id, week)

    subtasks = await create_decomposed_subtasks(
        session,
        member_id=parent.member_id,
        parent_task=parent,
        next_week_id=nxt.id,
        step_texts=["Собрать тексты", "Сверстать черновик"],
    )

    assert len(subtasks) == 2
    assert all(t.source == TaskSource.decomposed for t in subtasks)
    assert all(t.parent_task_id == parent.id for t in subtasks)
    assert all(t.week_id == nxt.id for t in subtasks)
    assert parent.status == TaskStatus.decomposed

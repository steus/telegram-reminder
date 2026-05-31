"""Вступление в группу: invite-код, имя, approve/reject."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import (
    Base,
    Member,
    MembershipRequestStatus,
    Task,
)
from app.db.repo import (
    approve_membership_request,
    create_group,
    create_member,
    create_membership_request,
    create_tasks,
    delete_member,
    generate_invite_code,
    get_group_by_invite_code,
    get_member_by_chat_id,
    get_pending_membership_request_by_chat,
    get_or_create_current_week,
    reject_membership_request,
)
from app.services.membership import (
    build_invite_link,
    parse_start_invite_code,
    validate_member_name_latin,
)


def test_parse_start_invite_code() -> None:
    assert parse_start_invite_code("join_a1b2c3d4") == "a1b2c3d4"
    assert parse_start_invite_code("JOIN_abc") == "abc"
    assert parse_start_invite_code(None) is None
    assert parse_start_invite_code("hello") is None


def test_validate_member_name_latin() -> None:
    assert validate_member_name_latin("Stepan")
    assert validate_member_name_latin("Ivan Petrov")
    assert not validate_member_name_latin("Степан")
    assert not validate_member_name_latin("A")
    assert not validate_member_name_latin("")


def test_build_invite_link() -> None:
    assert build_invite_link("my_bot", "deadbeef") == "https://t.me/my_bot?start=join_deadbeef"


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        group = await create_group(
            sess,
            name="Test Group",
            facilitator_chat_ids=["900"],
        )
        await sess.commit()
        yield sess, group

    await engine.dispose()


@pytest.mark.asyncio
async def test_membership_request_flow(session) -> None:
    sess, group = session

    request = await create_membership_request(
        sess,
        group_id=group.id,
        telegram_chat_id="100",
        full_name="Stepan",
        telegram_username="stepan",
    )
    await sess.commit()

    pending = await get_pending_membership_request_by_chat(sess, "100")
    assert pending is not None
    assert pending.id == request.id

    member = await approve_membership_request(
        sess,
        pending,
        resolved_by_chat_id="900",
    )
    await sess.commit()

    assert member.full_name == "Stepan"
    assert member.group_id == group.id
    assert pending.status == MembershipRequestStatus.approved

    again = await get_pending_membership_request_by_chat(sess, "100")
    assert again is None


@pytest.mark.asyncio
async def test_reject_allows_new_request(session) -> None:
    sess, group = session

    request = await create_membership_request(
        sess,
        group_id=group.id,
        telegram_chat_id="101",
        full_name="Anna",
    )
    await reject_membership_request(sess, request, resolved_by_chat_id="900")
    await sess.commit()

    assert request.status == MembershipRequestStatus.rejected

    new_request = await create_membership_request(
        sess,
        group_id=group.id,
        telegram_chat_id="101",
        full_name="Anna",
    )
    await sess.commit()
    assert new_request.id != request.id
    assert new_request.status == MembershipRequestStatus.pending


@pytest.mark.asyncio
async def test_get_group_by_invite_code(session) -> None:
    sess, group = session
    found = await get_group_by_invite_code(sess, group.invite_code)
    assert found is not None
    assert found.id == group.id


def test_generate_invite_code_unique() -> None:
    codes = {generate_invite_code() for _ in range(20)}
    assert len(codes) == 20


@pytest.mark.asyncio
async def test_delete_member_removes_record(session) -> None:
    sess, group = session
    member = await create_member(
        sess,
        group_id=group.id,
        full_name="Lada",
        telegram_chat_id="200",
    )
    week = await get_or_create_current_week(sess, group.id)
    await create_tasks(sess, member_id=member.id, week_id=week.id, texts=["Task 1"])
    await sess.commit()

    assert await delete_member(sess, member) is True
    await sess.commit()

    assert await get_member_by_chat_id(sess, "200") is None
    tasks = await sess.execute(select(Task).where(Task.member_id == member.id))
    assert tasks.scalars().all() == []


@pytest.mark.asyncio
async def test_delete_last_facilitator_blocked(session) -> None:
    sess, group = session
    facilitator = await create_member(
        sess,
        group_id=group.id,
        full_name="Lead",
        telegram_chat_id="900",
    )
    await sess.commit()

    assert await delete_member(sess, facilitator) is False

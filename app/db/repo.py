"""Репозиторий — единственная точка доступа к БД для бизнес-логики (§7 ТЗ).

Хендлеры и сервисы не пишут SQL напрямую, а вызывают функции отсюда.
На этапе 0 — минимум для /start.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Group, Member


async def get_member_by_chat_id(
    session: AsyncSession, chat_id: str | int
) -> Member | None:
    """Найти участника по Telegram chat_id или вернуть None."""
    result = await session.execute(
        select(Member).where(Member.telegram_chat_id == str(chat_id))
    )
    return result.scalar_one_or_none()


async def get_group(session: AsyncSession, group_id: int) -> Group | None:
    return await session.get(Group, group_id)

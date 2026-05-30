#!/usr/bin/env python3
"""Создать тестовую группу и участника для локальной разработки (этап 1).

Пример:
  python scripts/seed_member.py --chat-id 123456789 --name "Иван"
  python scripts/seed_member.py --chat-id 123456789 --name "Иван" --group "Группа A"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Корень проекта в PYTHONPATH при запуске как scripts/seed_member.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import settings
from app.db.models import Group, Member
from app.db.repo import create_group, create_member, get_or_create_dialog_state
from app.db.session import get_session, engine


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed group + member for bot-tracker")
    parser.add_argument("--chat-id", required=True, help="Telegram chat_id участника")
    parser.add_argument("--name", required=True, help="Полное имя участника")
    parser.add_argument("--group", default="Тестовая группа", help="Название группы")
    parser.add_argument(
        "--facilitator-chat-id",
        default=None,
        help="chat_id ведущего (по умолчанию = chat-id участника)",
    )
    args = parser.parse_args()

    facilitator = args.facilitator_chat_id or args.chat_id

    async with get_session() as session:
        existing = await session.execute(
            select(Member).where(Member.telegram_chat_id == str(args.chat_id))
        )
        if existing.scalar_one_or_none():
            print(f"Участник с chat_id={args.chat_id} уже существует.")
            return

        group_result = await session.execute(
            select(Group).where(Group.name == args.group)
        )
        group = group_result.scalar_one_or_none()
        if group is None:
            group = await create_group(
                session,
                name=args.group,
                facilitator_chat_id=str(facilitator),
            )
            print(f"Создана группа #{group.id}: {group.name}")

        member = await create_member(
            session,
            group_id=group.id,
            full_name=args.name,
            telegram_chat_id=str(args.chat_id),
            timezone=settings.default_timezone,
        )
        await get_or_create_dialog_state(session, member.id)
        print(
            f"Создан участник #{member.id}: {member.full_name} "
            f"(chat_id={member.telegram_chat_id})"
        )
        print("Отправь боту /start для прохождения онбординга.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

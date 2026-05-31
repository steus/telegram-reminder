"""Сводка целей группы для ведущего."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.task_confirmation import format_task_list
from app.db.models import Group, InputMode, Member, Task, Week
from app.db.repo import list_active_members_for_group, list_tasks_for_member_week


def format_group_goals_report(
    group: Group,
    week: Week,
    members: list[Member],
    goals_by_member_id: dict[int, list[Task]],
) -> str:
    header = (
        f"Задачи группы «{group.name}» — неделя с {week.start_date.strftime('%d.%m.%Y')}:\n"
    )
    if not members:
        return header + "\nАктивных участников нет."

    blocks: list[str] = [header]
    for member in members:
        goals = goals_by_member_id.get(member.id, [])
        mode = "auto" if member.input_mode == InputMode.auto else "private"
        if not goals:
            blocks.append(f"\n{member.full_name} ({mode}): задач нет")
            continue
        if all(g.confirmed for g in goals):
            status_note = "подтверждены"
        elif any(g.confirmed for g in goals):
            status_note = "частично подтверждены"
        else:
            status_note = "черновик"
        blocks.append(f"\n{member.full_name} ({mode}, {status_note}):")
        blocks.append(format_task_list(goals, show_status=True))

    text = "\n".join(blocks)
    if len(text) > 4000:
        return text[:3990] + "\n… (обрезано — слишком длинный список)"
    return text


async def build_group_goals_report(
    session: AsyncSession,
    group: Group,
    week: Week,
) -> str:
    members = await list_active_members_for_group(session, group.id)
    goals_by_member_id: dict[int, list[Task]] = {}
    for member in members:
        goals_by_member_id[member.id] = await list_tasks_for_member_week(
            session, member.id, week.id
        )
    return format_group_goals_report(group, week, members, goals_by_member_id)

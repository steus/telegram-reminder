"""Синхронизация статусов goals в Google Sheets (вкладка «Прогресс»)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.command_names import CMD_GROUP_SYNC_GOALS
from app.bot.task_confirmation import format_task_list
from app.db.models import Group, Member, Visibility
from app.db.repo import (
    get_group,
    get_or_create_current_week,
    list_active_members_for_group,
    list_tasks_for_member_week,
)
from app.services.sheets import upsert_member_progress


@dataclass
class SheetSyncResult:
    ok: bool
    message: str
    synced_count: int = 0


def _no_sheet_message() -> str:
    return (
        "У группы не настроена таблица (sheet_id). "
        "Попроси администратора привязать Google Sheet."
    )


def _no_creds_message() -> str:
    return "Не настроен GOOGLE_SERVICE_ACCOUNT_JSON — запись в таблицу недоступна."


async def sync_member_goals_to_sheet(
    session: AsyncSession,
    member: Member,
) -> SheetSyncResult:
    if member.visibility != Visibility.group:
        return SheetSyncResult(
            ok=False,
            message=(
                "В общую таблицу попадают только участники с видимостью «Группе». "
                f"Смени в /settings или попроси ведущего /{CMD_GROUP_SYNC_GOALS}."
            ),
        )

    group = await get_group(session, member.group_id)
    if group is None or not group.sheet_id:
        return SheetSyncResult(ok=False, message=_no_sheet_message())

    week = await get_or_create_current_week(session, member.group_id)
    goals = await list_tasks_for_member_week(session, member.id, week.id)
    if not goals:
        return SheetSyncResult(
            ok=False,
            message="На эту неделю задач нет — нечего обновлять в таблице.",
        )

    goals_text = format_task_list(goals, show_status=True)
    written = await upsert_member_progress(
        group.sheet_id,
        member_id=member.id,
        week_start=week.start_date,
        member_name=member.full_name,
        tasks_text=goals_text,
    )
    if not written:
        return SheetSyncResult(ok=False, message=_no_creds_message())

    return SheetSyncResult(
        ok=True,
        message=(
            f"Обновил твои задачи на вкладке «Прогресс» "
            f"(неделя с {week.start_date.strftime('%d.%m.%Y')})."
        ),
        synced_count=1,
    )


async def sync_group_goals_to_sheet(
    session: AsyncSession,
    group: Group,
) -> SheetSyncResult:
    if not group.sheet_id:
        return SheetSyncResult(ok=False, message=_no_sheet_message())

    week = await get_or_create_current_week(session, group.id)
    members = await list_active_members_for_group(session, group.id)
    eligible = [m for m in members if m.visibility == Visibility.group]

    if not eligible:
        return SheetSyncResult(
            ok=False,
            message="Нет активных участников с видимостью «Группе» — в таблицу некого писать.",
        )

    synced = 0
    skipped_empty = 0
    write_failed = False
    for member in eligible:
        goals = await list_tasks_for_member_week(session, member.id, week.id)
        if not goals:
            skipped_empty += 1
            continue
        goals_text = format_task_list(goals, show_status=True)
        if await upsert_member_progress(
            group.sheet_id,
            member_id=member.id,
            week_start=week.start_date,
            member_name=member.full_name,
            tasks_text=goals_text,
        ):
            synced += 1
        else:
            write_failed = True
            break

    if write_failed and synced == 0:
        return SheetSyncResult(ok=False, message=_no_creds_message())
    if synced == 0:
        return SheetSyncResult(
            ok=False,
            message="У участников с видимостью «Группе» нет задач на эту неделю.",
        )

    note = f"Обновил задачи {synced} участник(ов) на вкладке «Прогресс»."
    if skipped_empty:
        note += f" Без задач на неделе: {skipped_empty}."
    return SheetSyncResult(ok=True, message=note, synced_count=synced)

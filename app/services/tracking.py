"""LLM-трекинг в чек-ине: разбор текстового/голосового ответа (§6.3, промпт 2)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dialog_context import DialogContext
from app.db.models import Member, Task, TaskStatus
from app.db.repo import (
    get_or_create_dialog_state,
    get_or_create_profile,
    list_tasks_for_member_week,
    update_dialog_context,
    update_task_status,
)
from app.llm.client import ask_llm
from app.llm.prompts import PROMPT_TRACKING, build_profile_context

logger = logging.getLogger(__name__)

_STATUSES_MARKER = "[STATUSES]"
_REPORT_READY_RE = re.compile(r"\[REPORT_READY\].*", re.DOTALL)

VALID_TRACKING_STATUSES = frozenset(
    {TaskStatus.done, TaskStatus.in_progress, TaskStatus.stuck}
)


@dataclass
class TrackingResult:
    reply_text: str
    updated_tasks: list[tuple[int, TaskStatus]]
    report_ready: bool
    newly_stuck_task_ids: list[int]
    raw_llm: str | None = None


def format_tasks_for_prompt(tasks: list[Task]) -> str:
    lines: list[str] = []
    for task in tasks:
        lines.append(f"- id={task.id}: {task.text} (текущий статус: {task.status.value})")
    return "\n".join(lines) if lines else "(задач нет)"


def parse_status_updates(raw: str) -> list[tuple[int, TaskStatus]]:
    idx = raw.find(_STATUSES_MARKER)
    if idx == -1:
        return []

    rest = raw[idx + len(_STATUSES_MARKER) :].strip()
    brace = rest.find("{")
    if brace == -1:
        return []

    try:
        data, _ = json.JSONDecoder().raw_decode(rest[brace:])
    except json.JSONDecodeError:
        logger.warning("Failed to parse [STATUSES] JSON near: %r", rest[brace : brace + 200])
        return []

    updates_raw = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(updates_raw, list):
        return []

    result: list[tuple[int, TaskStatus]] = []
    for item in updates_raw:
        if not isinstance(item, dict):
            continue
        task_id = item.get("task_id")
        status_raw = item.get("status")
        if task_id is None or status_raw is None:
            continue
        try:
            status = TaskStatus(str(status_raw))
        except ValueError:
            continue
        if status not in VALID_TRACKING_STATUSES:
            continue
        result.append((int(task_id), status))
    return result


def strip_machine_markers(text: str) -> str:
    idx = text.find(_STATUSES_MARKER)
    if idx != -1:
        text = text[:idx]
    cleaned = _REPORT_READY_RE.sub("", text)
    return cleaned.strip()


def build_tracking_messages(
    tasks: list[Task],
    history: list[dict[str, str]],
    *,
    profile_json: str = "{}",
) -> list[dict[str, str]]:
    profile = build_profile_context(profile_json)
    system = PROMPT_TRACKING.format(
        profile=profile,
        tasks=format_tasks_for_prompt(tasks),
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(history)
    return messages


async def apply_tracking_updates(
    session: AsyncSession,
    member_id: int,
    week_id: int,
    updates: list[tuple[int, TaskStatus]],
) -> list[tuple[int, TaskStatus]]:
    tasks = await list_tasks_for_member_week(session, member_id, week_id)
    task_ids = {t.id for t in tasks}
    applied: list[tuple[int, TaskStatus]] = []

    for task_id, status in updates:
        if task_id not in task_ids:
            continue
        task = await update_task_status(session, task_id, status)
        if task is not None:
            applied.append((task_id, status))
    return applied


async def process_checkin_message(
    session: AsyncSession,
    member: Member,
    week_id: int,
    user_text: str,
) -> TrackingResult:
    tasks = await list_tasks_for_member_week(session, member.id, week_id)
    dialog = await get_or_create_dialog_state(session, member.id)
    ctx = DialogContext.from_json(dialog.context_json)

    ctx.append_checkin_message("user", user_text)
    profile = await get_or_create_profile(session, member.id)
    messages = build_tracking_messages(
        tasks,
        ctx.checkin_messages or [],
        profile_json=profile.profile_json,
    )

    raw = await ask_llm(messages)
    updates = parse_status_updates(raw)
    report_ready = "[REPORT_READY]" in raw
    reply_text = strip_machine_markers(raw) or "Записал, спасибо."

    ctx.append_checkin_message("assistant", reply_text)
    await update_dialog_context(session, member.id, ctx.to_json())

    previous_status = {t.id: t.status for t in tasks}
    applied = await apply_tracking_updates(session, member.id, week_id, updates)

    newly_stuck = [
        task_id
        for task_id, status in applied
        if status == TaskStatus.stuck and previous_status.get(task_id) != TaskStatus.stuck
    ]

    return TrackingResult(
        reply_text=reply_text,
        updated_tasks=applied,
        report_ready=report_ready,
        newly_stuck_task_ids=newly_stuck,
        raw_llm=raw if report_ready else None,
    )

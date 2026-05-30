"""Переиспользуемый экран подтверждения задач (этап 2+, auto-режим на этапе 4)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Task, TaskStatus

STATUS_LABELS = {
    TaskStatus.pending: "⏳",
    TaskStatus.done: "✅",
    TaskStatus.in_progress: "🔄",
    TaskStatus.stuck: "⛔",
    TaskStatus.decomposed: "📋",
}


def format_task_list(tasks: list[Task], *, show_status: bool = False) -> str:
    if not tasks:
        return "Задач пока нет."
    lines: list[str] = []
    for idx, task in enumerate(tasks, start=1):
        prefix = f"{idx}. "
        if show_status:
            icon = STATUS_LABELS.get(task.status, "")
            confirmed = "" if task.confirmed else " (черновик)"
            lines.append(f"{prefix}{icon} {task.text}{confirmed}")
        else:
            lines.append(f"{prefix}{task.text}")
    return "\n".join(lines)


def confirmation_message(tasks: list[Task]) -> str:
    body = format_task_list(tasks)
    return (
        "Вот что получилось — проверь, всё ли так:\n\n"
        f"{body}\n\n"
        "Если что-то не так — поправь. Когда всё ок — подтверди."
    )


def kb_task_confirmation(week_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Всё верно",
                    callback_data=f"tk:ok:{week_id}",
                ),
                InlineKeyboardButton(
                    text="✏️ Поправить",
                    callback_data=f"tk:ed:{week_id}",
                ),
            ]
        ]
    )

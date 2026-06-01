"""Статистика прогресса — чистая логика (§6.6)."""

from datetime import date

from app.db.models import Task, TaskStatus, Week
from app.services.stats import (
    WeekProgress,
    compute_closed_week_streak,
    compute_member_progress,
    format_stats_message,
)


def _task(
    week: Week,
    *,
    text: str,
    status: TaskStatus = TaskStatus.pending,
    confirmed: bool = True,
    task_id: int = 1,
) -> Task:
    return Task(
        id=task_id,
        member_id=1,
        week_id=week.id,
        text=text,
        status=status,
        confirmed=confirmed,
        week=week,
    )


def test_streak_consecutive_closed_weeks() -> None:
    weeks = [
        WeekProgress(1, date(2026, 5, 10), False, 2, 2),
        WeekProgress(2, date(2026, 5, 17), False, 2, 1),
        WeekProgress(3, date(2026, 5, 24), True, 1, 0),
    ]
    assert compute_closed_week_streak(weeks) == 2


def test_streak_breaks_on_gap() -> None:
    weeks = [
        WeekProgress(1, date(2026, 5, 3), False, 1, 1),
        WeekProgress(2, date(2026, 5, 17), False, 1, 1),
    ]
    assert compute_closed_week_streak(weeks) == 1


def test_completion_percent_and_recurring_stuck() -> None:
    w1 = Week(id=1, group_id=1, start_date=date(2026, 5, 10))
    w2 = Week(id=2, group_id=1, start_date=date(2026, 5, 17))
    current = Week(id=3, group_id=1, start_date=date(2026, 5, 24))
    tasks = [
        _task(w1, text="Звонок клиенту", status=TaskStatus.done, task_id=1),
        _task(w1, text="Отчёт", status=TaskStatus.done, task_id=2),
        _task(w2, text="Звонок клиенту", status=TaskStatus.stuck, task_id=3),
        _task(w2, text="Звонок клиенту", status=TaskStatus.stuck, task_id=4),
        _task(current, text="Новая цель", task_id=5),
    ]
    progress = compute_member_progress(tasks, current_week=current)
    assert progress.streak == 2
    w1_stats = next(w for w in progress.weeks if w.week_id == 1)
    assert w1_stats.percent == 100
    assert len(progress.recurring_stuck) == 1
    assert progress.recurring_stuck[0][1] == 2


def test_format_empty_history() -> None:
    text = format_stats_message(
        compute_member_progress([], current_week=None)
    )
    assert "Пока нет истории" in text

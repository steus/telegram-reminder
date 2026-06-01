"""Прогресс участника по истории задач (§6.6 ТЗ)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from app.db.models import Task, TaskStatus, Week

_DONE = TaskStatus.done
_TRACKED = frozenset(
    {TaskStatus.done, TaskStatus.in_progress, TaskStatus.stuck, TaskStatus.pending}
)
_STUCK_LIKE = frozenset({TaskStatus.stuck, TaskStatus.decomposed})


@dataclass(frozen=True)
class WeekProgress:
    week_id: int
    start_date: date
    is_current: bool
    total: int
    done: int

    @property
    def percent(self) -> int | None:
        if self.total == 0:
            return None
        return round(100 * self.done / self.total)


@dataclass(frozen=True)
class MemberProgress:
    streak: int
    weeks: list[WeekProgress]
    recurring_stuck: list[tuple[str, int]]


def _group_tasks_by_week(tasks: list[Task]) -> dict[int, tuple[Week, list[Task]]]:
    grouped: dict[int, tuple[Week, list[Task]]] = {}
    for task in tasks:
        week = task.week
        if week.id not in grouped:
            grouped[week.id] = (week, [])
        grouped[week.id][1].append(task)
    return grouped


def _week_counts(tasks: list[Task]) -> tuple[int, int]:
    """Считаем только подтверждённые задачи; done vs все отслеживаемые статусы."""
    confirmed = [t for t in tasks if t.confirmed]
    if not confirmed:
        return 0, 0
    total = sum(1 for t in confirmed if t.status in _TRACKED)
    done = sum(1 for t in confirmed if t.status == _DONE)
    return total, done


def compute_closed_week_streak(weeks: list[WeekProgress]) -> int:
    """Непрерывная серия закрытых недель с подтверждёнными задачами (от новой к старой)."""
    closed = sorted(
        (w for w in weeks if not w.is_current and w.total > 0),
        key=lambda w: w.start_date,
        reverse=True,
    )
    if not closed:
        return 0
    streak = 1
    for i in range(1, len(closed)):
        if (closed[i - 1].start_date - closed[i].start_date).days == 7:
            streak += 1
        else:
            break
    return streak


def _weeks_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "неделя"
    if 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return "недели"
    return "недель"


def compute_member_progress(
    tasks: list[Task], *, current_week: Week | None
) -> MemberProgress:
    grouped = _group_tasks_by_week(tasks)
    current_id = current_week.id if current_week else None

    weeks: list[WeekProgress] = []
    for week, week_tasks in sorted(grouped.values(), key=lambda x: x[0].start_date):
        total, done = _week_counts(week_tasks)
        weeks.append(
            WeekProgress(
                week_id=week.id,
                start_date=week.start_date,
                is_current=week.id == current_id,
                total=total,
                done=done,
            )
        )

    stuck_counts: dict[str, int] = defaultdict(int)
    display_text: dict[str, str] = {}
    for task in tasks:
        if not task.confirmed or task.status not in _STUCK_LIKE:
            continue
        key = " ".join(task.text.split()).lower()
        if not key:
            continue
        stuck_counts[key] += 1
        display_text[key] = task.text.strip()

    recurring = sorted(
        ((display_text[k], c) for k, c in stuck_counts.items() if c >= 2),
        key=lambda x: (-x[1], x[0]),
    )[:5]

    streak = compute_closed_week_streak(weeks)
    return MemberProgress(streak=streak, weeks=weeks, recurring_stuck=recurring)


def format_stats_message(progress: MemberProgress) -> str:
    if not progress.weeks:
        return (
            "Пока нет истории по неделям — как появятся задачи и чек-ины, "
            "здесь соберётся прогресс."
        )

    lines = ["Твой прогресс по неделям.\n"]

    if progress.streak > 0:
        w = progress.streak
        lines.append(f"Серия закрытых недель подряд: {w} {_weeks_word(w)}.\n")
    else:
        lines.append("Серия закрытых недель: пока без непрерывной цепочки.\n")

    lines.append("Выполнение по неделям:")
    shown = [w for w in progress.weeks if w.total > 0][-8:]
    if not shown:
        lines.append("— пока нет подтверждённых задач.")
    else:
        for w in shown:
            label = w.start_date.strftime("%d.%m.%Y")
            if w.is_current:
                label += " (текущая)"
            pct = w.percent
            if pct is None:
                lines.append(f"• {label}: задач пока нет")
            else:
                lines.append(f"• {label}: {pct}% ({w.done} из {w.total})")

    if progress.recurring_stuck:
        lines.append("\nЧаще всего в затыке или с декомпозицией:")
        for text, count in progress.recurring_stuck:
            short = text if len(text) <= 60 else text[:57] + "…"
            lines.append(f"• «{short}» — {count} раз")

    return "\n".join(lines)

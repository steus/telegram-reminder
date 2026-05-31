"""Сводка goals группы для ведущего."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.db.models import InputMode, TaskStatus
from app.services.group_goals_view import format_group_goals_report


def test_format_group_goals_report_includes_members() -> None:
    group = MagicMock(name="Тест", id=1)
    week = MagicMock(start_date=date(2026, 5, 30))
    m1 = MagicMock(id=1, full_name="Иван", input_mode=InputMode.private)
    m2 = MagicMock(id=2, full_name="Мария", input_mode=InputMode.auto)
    g1 = MagicMock(text="Goal A", confirmed=True, status=TaskStatus.pending)
    g2 = MagicMock(text="Goal B", confirmed=False, status=TaskStatus.pending)

    text = format_group_goals_report(
        group,
        week,
        [m1, m2],
        {1: [g1], 2: [g2]},
    )
    assert "Иван" in text
    assert "Мария" in text
    assert "Goal A" in text
    assert "черновик" in text

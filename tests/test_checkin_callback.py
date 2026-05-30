"""Парсинг callback_data чек-ина и лимит 64 байт (§6.4)."""

from __future__ import annotations

from app.bot.keyboards import checkin_callback_data
from app.bot.routers.checkin import parse_checkin_callback
from app.db.models import TaskStatus


def test_parse_checkin_callback_valid() -> None:
    assert parse_checkin_callback("t:42:done") == (42, TaskStatus.done)
    assert parse_checkin_callback("t:1:in_progress") == (1, TaskStatus.in_progress)
    assert parse_checkin_callback("t:999:stuck") == (999, TaskStatus.stuck)


def test_parse_checkin_callback_invalid() -> None:
    assert parse_checkin_callback("tk:ok:1") is None
    assert parse_checkin_callback("t:1:pending") is None
    assert parse_checkin_callback("t:abc:done") is None


def test_callback_data_within_telegram_limit() -> None:
    for status in (TaskStatus.done, TaskStatus.in_progress, TaskStatus.stuck):
        data = checkin_callback_data(9_999_999, status)
        assert len(data.encode("utf-8")) <= 64
        assert data == f"t:9999999:{status.value}"

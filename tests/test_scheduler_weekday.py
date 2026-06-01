"""Логика дня встречи относительно чек-ина."""

from app.scheduler import meeting_weekday, midweek_weekday, slot_key
from datetime import datetime


def test_meeting_weekday_after_checkin() -> None:
    assert meeting_weekday(4) == 5  # пт чек-ин → сб встреча
    assert meeting_weekday(6) == 0  # вс → пн


def test_midweek_three_days_after_meeting() -> None:
    assert midweek_weekday(4) == 1  # пт чек-ин → сб встреча → вт середина


def test_slot_key_stable() -> None:
    dt = datetime(2026, 5, 30, 18, 0)
    assert slot_key(3, dt, "checkin") == "checkin:3:2026-05-30-18-00"

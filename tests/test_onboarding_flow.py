"""Парсинг времени чек-ина в онбординге и настройках."""

from __future__ import annotations

from datetime import time

from app.bot.onboarding_flow import parse_checkin_time, parse_time_callback_data


def test_parse_checkin_time() -> None:
    assert parse_checkin_time("19:30") == time(19, 30)
    assert parse_checkin_time("9:05") == time(9, 5)
    assert parse_checkin_time("invalid") is None


def test_parse_time_callback_data() -> None:
    assert parse_time_callback_data("ob:tm:18:00", "ob:tm") == time(18, 0)
    assert parse_time_callback_data("st:tm:09:30", "st:tm") == time(9, 30)
    assert parse_time_callback_data("ob:tm:custom", "ob:tm") is None

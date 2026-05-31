"""Парсинг LLM-трекинга и callback декомпозиции."""

from __future__ import annotations

from app.bot.keyboards import decompose_offer_callback, kb_decompose_offer
from app.db.models import TaskStatus
from app.services.tracking import parse_status_updates, strip_machine_markers


def test_parse_status_updates_valid() -> None:
    raw = (
        "Отлично, вижу прогресс.\n"
        '[STATUSES] {"updates": [{"task_id": 3, "status": "done"}, '
        '{"task_id": 5, "status": "stuck"}]}'
    )
    assert parse_status_updates(raw) == [
        (3, TaskStatus.done),
        (5, TaskStatus.stuck),
    ]


def test_parse_status_updates_ignores_invalid() -> None:
    raw = '[STATUSES] {"updates": [{"task_id": 1, "status": "pending"}]}'
    assert parse_status_updates(raw) == []


def test_strip_machine_markers() -> None:
    raw = (
        "Спасибо!\n"
        '[STATUSES] {"updates": []}\n'
        "[REPORT_READY]\nИтог: всё ок."
    )
    assert strip_machine_markers(raw) == "Спасибо!"


def test_decompose_callback_within_limit() -> None:
    data = decompose_offer_callback(999_999, True)
    assert data == "dc:yn:yes:999999"
    assert len(data.encode("utf-8")) <= 64
    markup = kb_decompose_offer(123)
    assert markup.inline_keyboard[0][0].callback_data == "dc:yn:yes:123"

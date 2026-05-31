"""Итог недели: разбор маркера и маршрутизация видимости."""

from __future__ import annotations

from app.bot.keyboards import kb_summary_send, summary_send_callback
from app.db.models import SharedScope, Visibility
from app.services.summary import (
    split_report_ready,
    visibility_to_shared_scope,
)


def test_split_report_ready() -> None:
    raw = (
        "Спасибо за ответ!\n"
        "[STATUSES] {\"updates\": []}\n"
        "[REPORT_READY]\nСделано 3 из 5. Затык: найм."
    )
    dialog, facilitator = split_report_ready(raw)
    assert "Спасибо" in dialog
    assert "[REPORT_READY]" not in dialog
    assert "[STATUSES]" not in dialog
    assert facilitator.startswith("Сделано")


def test_visibility_to_shared_scope() -> None:
    assert visibility_to_shared_scope(Visibility.group, confirmed=True) == SharedScope.group
    assert (
        visibility_to_shared_scope(Visibility.facilitator, confirmed=True)
        == SharedScope.facilitator
    )
    assert (
        visibility_to_shared_scope(Visibility.private, confirmed=True)
        == SharedScope.private
    )
    assert visibility_to_shared_scope(Visibility.group, confirmed=False) == SharedScope.none


def test_summary_callback_within_limit() -> None:
    assert summary_send_callback(True) == "sm:yn:yes"
    assert len(summary_send_callback(False).encode("utf-8")) <= 64
    markup = kb_summary_send()
    assert markup.inline_keyboard[0][0].callback_data == "sm:yn:yes"

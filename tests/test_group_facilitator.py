"""Парсинг chat_id ведущих."""

from app.db.repo import parse_facilitator_chat_ids


def test_parse_single() -> None:
    assert parse_facilitator_chat_ids("379481763") == ["379481763"]


def test_parse_comma_separated() -> None:
    assert parse_facilitator_chat_ids("111, 222,111") == ["111", "222"]


def test_parse_multiple_args() -> None:
    assert parse_facilitator_chat_ids("111", "222") == ["111", "222"]


def test_parse_default() -> None:
    assert parse_facilitator_chat_ids(default="999") == ["999"]

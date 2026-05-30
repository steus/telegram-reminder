"""Юнит-тесты LLM-фолбэка и парсинга извлечения."""

from __future__ import annotations

import asyncio

import pytest

from app.llm.client import ask_llm, reset_providers_for_testing, set_providers_for_testing
from app.services.extraction import parse_json_string_array


class _MockProvider:
    def __init__(self, response: str, *, fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.calls = 0

    async def complete(self, messages, *, json_mode: bool = False) -> str:
        self.calls += 1
        if self.fail:
            raise TimeoutError("primary timeout")
        return self.response


@pytest.fixture(autouse=True)
def _reset_llm_overrides():
    yield
    reset_providers_for_testing()


@pytest.mark.asyncio
async def test_ask_llm_falls_back_on_primary_timeout() -> None:
    primary = _MockProvider("", fail=True)
    fallback = _MockProvider('["задача от фолбэка"]')
    set_providers_for_testing(primary, fallback)

    result = await ask_llm([{"role": "user", "content": "test"}], json_mode=True)

    assert result == '["задача от фолбэка"]'
    assert primary.calls == 1
    assert fallback.calls == 1


def test_parse_json_string_array_plain() -> None:
    assert parse_json_string_array('["a", "b"]') == ["a", "b"]


def test_parse_json_string_array_with_fence() -> None:
    raw = '```json\n["одна", "две"]\n```'
    assert parse_json_string_array(raw) == ["одна", "две"]


def test_parse_json_string_array_wrapped_object() -> None:
    raw = '{"tasks": ["x", "y"]}'
    assert parse_json_string_array(raw) == ["x", "y"]


def test_parse_json_string_array_invalid() -> None:
    assert parse_json_string_array("not json") == []

"""Настройки email/телефона в /settings."""

from __future__ import annotations

from datetime import time

import pytest

from app.bot import keyboards as kb
from app.db.models import InputMode, Member, Visibility
from app.instance_config import InstanceConfig, OnboardingConfig


def _member(**overrides) -> Member:
    defaults = dict(
        id=1,
        group_id=1,
        full_name="Stepan",
        telegram_chat_id="100",
        input_mode=InputMode.private,
        visibility=Visibility.private,
        checkin_weekday=0,
        checkin_time=time(12, 0),
        timezone="Europe/Tallinn",
        midweek_ping=True,
        is_active=True,
        email=None,
        phone=None,
    )
    defaults.update(overrides)
    return Member(**defaults)


def test_format_member_settings_shows_contacts_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = InstanceConfig(onboarding=OnboardingConfig(collect_email=True, collect_phone=True))
    monkeypatch.setattr("app.bot.keyboards.load_instance_config", lambda: cfg)

    text = kb.format_member_settings(
        _member(email="stepan@example.com", phone="+79001234567")
    )
    assert "Email: stepan@example.com" in text
    assert "Телефон: +79001234567" in text


def test_format_member_settings_hides_contacts_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = InstanceConfig()
    monkeypatch.setattr("app.bot.keyboards.load_instance_config", lambda: cfg)

    text = kb.format_member_settings(_member(email="stepan@example.com"))
    assert "Email:" not in text
    assert "Телефон:" not in text


def test_kb_settings_menu_includes_contact_buttons_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = InstanceConfig(onboarding=OnboardingConfig(collect_email=True, collect_phone=True))
    monkeypatch.setattr("app.bot.keyboards.load_instance_config", lambda: cfg)

    markup = kb.kb_settings_menu()
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "st:ed:email" in callbacks
    assert "st:ed:phone" in callbacks


def test_kb_settings_menu_excludes_contact_buttons_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = InstanceConfig()
    monkeypatch.setattr("app.bot.keyboards.load_instance_config", lambda: cfg)

    markup = kb.kb_settings_menu()
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "st:ed:email" not in callbacks
    assert "st:ed:phone" not in callbacks

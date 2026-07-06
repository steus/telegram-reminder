"""Конфиг инстанса и контактные поля онбординга."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.bot.dialog_context import DialogContext
from app.bot.onboarding_flow import parse_email, parse_phone
from app.instance_config import (
    InstanceConfig,
    OnboardingConfig,
    clear_instance_config_cache,
    get_onboarding_steps,
    parse_instance_config,
)


def test_default_onboarding_steps() -> None:
    cfg = InstanceConfig()
    assert get_onboarding_steps(cfg) == (
        "input_mode",
        "visibility",
        "weekday",
        "time",
        "ping",
    )


def test_marina_onboarding_steps() -> None:
    cfg = InstanceConfig(
        onboarding=OnboardingConfig(collect_email=True, collect_phone=True),
    )
    assert get_onboarding_steps(cfg) == (
        "input_mode",
        "visibility",
        "email",
        "phone",
        "weekday",
        "time",
        "ping",
    )


def test_advance_onboarding_with_contact_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = InstanceConfig(
        onboarding=OnboardingConfig(collect_email=True, collect_phone=True),
    )
    steps = get_onboarding_steps(cfg)
    monkeypatch.setattr(
        "app.bot.dialog_context.get_onboarding_steps",
        lambda: steps,
    )
    ctx = DialogContext()
    ctx.start_onboarding()
    assert ctx.step == steps[0]
    for step in steps[1:]:
        assert ctx.advance_onboarding() is False
        assert ctx.step == step
    assert ctx.advance_onboarding() is True
    assert ctx.onboarded is True


def test_parse_email() -> None:
    assert parse_email("user@example.com") == "user@example.com"
    assert parse_email(" bad@mail.ru ") == "bad@mail.ru"
    assert parse_email("not-an-email") is None


def test_parse_phone() -> None:
    assert parse_phone("+372 51234567") == "+37251234567"
    assert parse_phone("89001234567") == "89001234567"
    assert parse_phone("51234567") == "51234567"
    assert parse_phone("123456") is None
    assert parse_phone("123") is None


def test_load_instance_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps(
            {
                "id": "test",
                "onboarding": {"collect_email": True, "collect_phone": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("INSTANCE_CONFIG", str(path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    clear_instance_config_cache()

    from importlib import reload

    import app.config as config_module
    import app.instance_config as instance_config_module

    reload(config_module)
    reload(instance_config_module)

    cfg = instance_config_module.load_instance_config()
    assert cfg.id == "test"
    assert cfg.onboarding.collect_email is True
    assert cfg.onboarding.collect_phone is False
    assert instance_config_module.get_onboarding_steps(cfg) == (
        "input_mode",
        "visibility",
        "email",
        "weekday",
        "time",
        "ping",
    )


def test_parse_instance_config() -> None:
    cfg = parse_instance_config(
        {
            "id": "x",
            "onboarding": {"collect_email": True},
            "features": {"jtbd_profile": True},
        }
    )
    assert cfg.id == "x"
    assert cfg.onboarding.collect_email is True
    assert cfg.features.jtbd_profile is True

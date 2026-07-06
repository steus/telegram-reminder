"""Конфигурация инстанса бота — какие фичи и шаги онбординга включены.

Файл задаётся через INSTANCE_CONFIG (путь к JSON относительно корня проекта
или абсолютный). По умолчанию — config/instances/default.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_BASE_ONBOARDING_STEPS = ("input_mode", "visibility", "weekday", "time", "ping")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "instances" / "default.json"


@dataclass(frozen=True)
class OnboardingConfig:
    collect_email: bool = False
    collect_phone: bool = False


@dataclass(frozen=True)
class FeaturesConfig:
    jtbd_profile: bool = False


@dataclass(frozen=True)
class InstanceConfig:
    id: str = "default"
    onboarding: OnboardingConfig = OnboardingConfig()
    features: FeaturesConfig = FeaturesConfig()


def _resolve_config_path(path: str | None) -> Path:
    if not path:
        return _DEFAULT_CONFIG_PATH
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _PROJECT_ROOT / candidate


def _load_raw_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Instance config not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Instance config must be a JSON object: {path}")
    return data


def parse_instance_config(raw: dict) -> InstanceConfig:
    onboarding_raw = raw.get("onboarding") or {}
    features_raw = raw.get("features") or {}
    if not isinstance(onboarding_raw, dict):
        onboarding_raw = {}
    if not isinstance(features_raw, dict):
        features_raw = {}
    return InstanceConfig(
        id=str(raw.get("id") or "default"),
        onboarding=OnboardingConfig(
            collect_email=bool(onboarding_raw.get("collect_email", False)),
            collect_phone=bool(onboarding_raw.get("collect_phone", False)),
        ),
        features=FeaturesConfig(
            jtbd_profile=bool(features_raw.get("jtbd_profile", False)),
        ),
    )


@lru_cache
def load_instance_config() -> InstanceConfig:
    from app.config import settings

    path = _resolve_config_path(settings.instance_config)
    try:
        return parse_instance_config(_load_raw_config(path))
    except FileNotFoundError:
        if path != _DEFAULT_CONFIG_PATH:
            raise
        return parse_instance_config({})


def get_onboarding_steps(config: InstanceConfig | None = None) -> tuple[str, ...]:
    """Активные шаги онбординга с учётом конфига инстанса."""
    cfg = config or load_instance_config()
    steps: list[str] = []
    for step in _BASE_ONBOARDING_STEPS:
        if step == "weekday":
            if cfg.onboarding.collect_email:
                steps.append("email")
            if cfg.onboarding.collect_phone:
                steps.append("phone")
        steps.append(step)
    return tuple(steps)


def clear_instance_config_cache() -> None:
    load_instance_config.cache_clear()

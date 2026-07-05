"""JTBD-анкета: парсеры, валидатор, прогресс, build_profile_context."""

from __future__ import annotations

import json

from app.llm.prompts import build_profile_context
from app.services.profile_onboarding import (
    REQUIRED_FIELD_KEYS,
    count_filled_fields,
    format_progress_line,
    parse_profile_ready,
    parse_state_marker,
    strip_survey_markers,
    validate_required_fields,
)


def _sample_profile() -> dict:
    return {
        "business": {
            "niche": "EdTech",
            "product": "Курсы",
            "customer": "",
            "model": "",
            "stage": "первые продажи",
            "team": "",
        },
        "economics": {
            "revenue_range": "",
            "avg_check": "",
            "tracked_metrics": "",
            "bottleneck": "мало лидов",
        },
        "channels": {"sales_channels": "", "crm_tools": "", "payments": ""},
        "social": {"networks": [], "paid_traffic": "", "ad_budget": ""},
        "goals": {
            "year_goal": "100k выручки",
            "emotional_job": "",
            "success_criteria": "100 клиентов",
            "quarter_goal": "запустить воронку",
            "quarter_deadline": "",
        },
        "style": {
            "hours_per_week": "5",
            "planning_habit": "",
            "needs_push_on": "",
        },
    }


def test_validate_required_fields_complete() -> None:
    assert validate_required_fields(_sample_profile()) == []


def test_validate_required_fields_missing() -> None:
    data = _sample_profile()
    data["business"]["niche"] = ""
    missing = validate_required_fields(data)
    assert "niche" in missing
    assert len(missing) == 1


def test_validate_required_fields_incomplete_not_saved() -> None:
    data = _sample_profile()
    data["goals"]["quarter_goal"] = ""
    missing = validate_required_fields(data)
    assert "quarter_goal" in missing
    assert len(missing) >= 1


def test_parse_state_marker() -> None:
    raw = 'Понял.\n[STATE]{"block": 3, "filled": ["niche", "product", "stage"]}'
    parsed = parse_state_marker(raw)
    assert parsed is not None
    assert parsed["block"] == 3
    assert parsed["filled"] == ["niche", "product", "stage"]


def test_parse_profile_ready_json() -> None:
    profile = _sample_profile()
    raw = f"Всё верно?\n[ПРОФИЛЬ_ГОТОВ]{json.dumps(profile, ensure_ascii=False)}"
    parsed = parse_profile_ready(raw)
    assert parsed is not None
    assert parsed["business"]["niche"] == "EdTech"


def test_strip_survey_markers() -> None:
    raw = (
        "Отлично, идём дальше.\n"
        '[STATE]{"block": 2, "filled": ["niche"]}\n'
        "[ПРОФИЛЬ_ГОТОВ]{}"
    )
    assert strip_survey_markers(raw) == "Отлично, идём дальше."


def test_count_filled_fields_and_progress_line() -> None:
    progress = {"block": 4, "filled": ["niche", "product", "stage", "bottleneck"]}
    assert count_filled_fields(progress) == 4
    line = format_progress_line(progress)
    assert "4/8" in line
    assert "блок 4 из 6" in line
    assert "пауза" in line.lower()


def test_build_profile_context_empty() -> None:
    text = build_profile_context("{}")
    assert "не заполнен" in text.lower()
    assert "не выдумывай" in text.lower()


def test_build_profile_context_full() -> None:
    text = build_profile_context(json.dumps(_sample_profile(), ensure_ascii=False))
    assert "EdTech" in text
    assert "100k выручки" in text
    assert "5" in text


def test_required_field_keys_count() -> None:
    assert len(REQUIRED_FIELD_KEYS) == 8

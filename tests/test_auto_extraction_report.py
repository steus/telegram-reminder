"""Отчёт ведущему и логика повторной рассылки."""

from app.services.auto_goal_setup import (
    AutoExtractionResult,
    REASON_NO_TASKS,
    REASON_NOT_ONBOARDED,
    format_facilitator_report,
)


def test_format_facilitator_report_with_assignments() -> None:
    result = AutoExtractionResult(
        sent_with_tasks=["Stepan Teus"],
        without_tasks=[("Maria", REASON_NO_TASKS)],
    )
    text = format_facilitator_report(result)
    assert "Stepan Teus" in text
    assert "Maria" in text
    assert REASON_NO_TASKS in text


def test_format_facilitator_report_saved_only() -> None:
    text = format_facilitator_report(AutoExtractionResult(), saved_only=True)
    assert "ничего не отправлено" in text


def test_format_facilitator_report_no_auto() -> None:
    result = AutoExtractionResult(no_auto_members=True)
    text = format_facilitator_report(result)
    assert "Нет участников в режиме auto" in text


def test_format_facilitator_report_not_onboarded() -> None:
    result = AutoExtractionResult(
        without_tasks=[("Ivan", REASON_NOT_ONBOARDED)],
    )
    text = format_facilitator_report(result)
    assert "Ivan" in text
    assert REASON_NOT_ONBOARDED in text

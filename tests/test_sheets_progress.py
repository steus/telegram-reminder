"""Сопоставление строк вкладки «Прогресс» — без gspread."""

from datetime import date

from app.services.sheets import (
    _find_progress_row_indices,
    _normalize_member_name,
    _parse_week_cell,
    _progress_row_matches,
    progress_row_key,
)


def test_parse_week_cell_iso() -> None:
    assert _parse_week_cell("2025-05-26") == "2025-05-26"


def test_parse_week_cell_european() -> None:
    assert _parse_week_cell("26.05.2025") == "2025-05-26"


def test_parse_week_cell_us() -> None:
    assert _parse_week_cell("5/26/2025") == "2025-05-26"


def test_progress_row_key_stable() -> None:
    week = date(2025, 5, 26)
    assert progress_row_key(42, week) == "pr:42:2025-05-26"


def test_progress_row_matches_different_date_format() -> None:
    week = date(2025, 5, 26).isoformat()
    member = _normalize_member_name("Stepan Teus")
    row = ["26.05.2025", "Stepan Teus", "2025-05-31", "1. task"]
    assert _progress_row_matches(row, week, member)


def test_find_by_row_key() -> None:
    week = date(2025, 5, 26)
    key = progress_row_key(7, week)
    rows = [
        ["Ключ", "Неделя", "Участник", "Обновлено", "Задачи (статусы)"],
        [key, "2025-05-26", "Stepan", "ts", "tasks"],
        [key, "2025-05-26", "Stepan", "ts2", "dup"],
    ]
    found = _find_progress_row_indices(
        rows,
        row_key=key,
        week_iso=week.isoformat(),
        member_norm=_normalize_member_name("Stepan"),
    )
    assert found == [2, 3]


def test_find_legacy_row_without_key() -> None:
    week = date(2025, 5, 26)
    key = progress_row_key(7, week)
    rows = [
        ["Неделя", "Участник", "Обновлено", "Задачи (статусы)"],
        ["26.05.2025", "Stepan Teus", "ts", "tasks"],
    ]
    found = _find_progress_row_indices(
        rows,
        row_key=key,
        week_iso=week.isoformat(),
        member_norm=_normalize_member_name("Stepan Teus"),
    )
    assert found == [2]


def test_find_skips_other_member_keys() -> None:
    week = date(2025, 5, 26)
    key = progress_row_key(7, week)
    other_key = progress_row_key(99, week)
    rows = [
        list("abcde"),
        [other_key, week.isoformat(), "Other", "ts", "x"],
    ]
    found = _find_progress_row_indices(
        rows,
        row_key=key,
        week_iso=week.isoformat(),
        member_norm=_normalize_member_name("Stepan"),
    )
    assert found == []

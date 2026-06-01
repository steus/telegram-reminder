"""Синхронизация задач в Sheets — проверки без gspread."""

from __future__ import annotations

from app.db.models import Visibility
from app.services.sheet_sync import SheetSyncResult
from app.services.sheets import spreadsheet_edit_url


def test_sheet_sync_result_defaults() -> None:
    r = SheetSyncResult(ok=True, message="ok")
    assert r.synced_count == 0


def test_group_visibility_enum() -> None:
    assert Visibility.group.value == "group"


def test_spreadsheet_edit_url() -> None:
    assert spreadsheet_edit_url("abc123") == (
        "https://docs.google.com/spreadsheets/d/abc123/edit"
    )

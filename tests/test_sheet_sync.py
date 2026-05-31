"""Синхронизация задач в Sheets — проверки без gspread."""

from __future__ import annotations

from app.db.models import Visibility
from app.services.sheet_sync import SheetSyncResult


def test_sheet_sync_result_defaults() -> None:
    r = SheetSyncResult(ok=True, message="ok")
    assert r.synced_count == 0


def test_group_visibility_enum() -> None:
    assert Visibility.group.value == "group"

"""Диагностика credentials Google Sheets."""

from __future__ import annotations

from pathlib import Path

from app.services.sheets import _resolve_credentials_path, sheets_credentials_problem


def test_resolve_credentials_path_absolute(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text('{"type":"service_account"}', encoding="utf-8")
    assert _resolve_credentials_path(str(sa)) == sa


def test_resolve_credentials_path_relative(tmp_path: Path, monkeypatch) -> None:
    sa = tmp_path / "cred.json"
    sa.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _resolve_credentials_path("cred.json").resolve() == sa.resolve()


def test_sheets_credentials_problem_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.sheets.settings.google_service_account_json",
        None,
    )
    msg = sheets_credentials_problem()
    assert msg is not None
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in msg


def test_sheets_credentials_problem_bad_inline_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.sheets.settings.google_service_account_json",
        '{ "type": "service_account", broken',
    )
    msg = sheets_credentials_problem()
    assert msg is not None
    assert "битый" in msg or "JSON" in msg

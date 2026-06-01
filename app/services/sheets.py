"""Google Sheets — витрина финальных сводок (§11 ТЗ)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_PROGRESS_TAB = "Прогресс"


def spreadsheet_edit_url(sheet_id: str) -> str:
    """Публичная ссылка на таблицу группы (открывается в браузере)."""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


_SUMMARY_HEADERS = (
    "Неделя",
    "Участник",
    "Сводка участника",
    "Резюме для ведущего",
)
_PROGRESS_HEADERS = (
    "Ключ",
    "Неделя",
    "Участник",
    "Обновлено",
    "Задачи (статусы)",
)

_LEGACY_PROGRESS_HEADERS = _PROGRESS_HEADERS[1:]

_WEEK_CELL_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d.%m.%y",
    "%m/%d/%Y",
    "%d/%m/%Y",
)

_upsert_locks: dict[tuple[str, str, int], asyncio.Lock] = {}


def progress_row_key(member_id: int, week_start: date) -> str:
    """Стабильный ключ строки: member_id + неделя (не зависит от формата даты в Sheets)."""
    return f"pr:{member_id}:{week_start.isoformat()}"


def _normalize_member_name(name: str) -> str:
    return " ".join((name or "").split()).casefold()


def _parse_week_cell(value: str) -> str | None:
    """Привести ячейку «Неделя» к ISO YYYY-MM-DD для сравнения."""
    raw = (value or "").strip()
    if not raw or raw.lower() == "неделя":
        return None
    for fmt in _WEEK_CELL_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _progress_row_matches(row: list[str], week_iso: str, member_norm: str) -> bool:
    """Сопоставление legacy-строк (4 колонки, без «Ключ»)."""
    if len(row) < 2:
        return False
    row_week = _parse_week_cell(row[0])
    if row_week != week_iso:
        return False
    return _normalize_member_name(row[1]) == member_norm


def _find_progress_row_indices(
    all_rows: list[list[str]],
    *,
    row_key: str,
    week_iso: str,
    member_norm: str,
) -> list[int]:
    """1-based номера строк (кроме заголовка), подходящих под upsert."""
    matches: list[int] = []
    for idx, row in enumerate(all_rows[1:], start=2):
        if not row:
            continue
        cell0 = (row[0] or "").strip()
        if cell0 == row_key:
            matches.append(idx)
            continue
        if cell0.startswith("pr:"):
            continue
        # legacy 4-col или строка без ключа
        if len(row) >= 4 and not cell0.startswith("pr:"):
            legacy = row[:4]
        else:
            legacy = row
        if _progress_row_matches(legacy, week_iso, member_norm):
            matches.append(idx)
    return matches


def _ensure_progress_headers(worksheet, existing: list[list[str]]) -> None:
    if not existing:
        worksheet.append_row(list(_PROGRESS_HEADERS), value_input_option="USER_ENTERED")
        return
    header = existing[0]
    if header == list(_PROGRESS_HEADERS):
        return
    if header == list(_LEGACY_PROGRESS_HEADERS):
        worksheet.update(
            "A1:E1",
            [list(_PROGRESS_HEADERS)],
            value_input_option="USER_ENTERED",
        )
        return
    if header and header[0] != "Ключ":
        worksheet.update(
            "A1:E1",
            [list(_PROGRESS_HEADERS)],
            value_input_option="USER_ENTERED",
        )


def _open_spreadsheet(sheet_id: str):
    import gspread
    from google.oauth2.service_account import Credentials

    info = _load_service_account_info()
    if info is None:
        raise RuntimeError("Google service account credentials are not configured")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def _get_progress_worksheet(spreadsheet):
    import gspread

    try:
        worksheet = spreadsheet.worksheet(_PROGRESS_TAB)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=_PROGRESS_TAB, rows=200, cols=5)
    existing = worksheet.get_all_values()
    _ensure_progress_headers(worksheet, existing)
    return worksheet


def _load_service_account_info() -> dict[str, Any] | None:
    raw = settings.google_service_account_json
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("{"):
        return json.loads(text)
    path = Path(text)
    if not path.is_file():
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is not a file: %s", path)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _append_row_sync(
    sheet_id: str,
    *,
    week_start: date,
    member_name: str,
    member_text: str,
    facilitator_text: str,
) -> None:
    spreadsheet = _open_spreadsheet(sheet_id)
    worksheet = spreadsheet.sheet1

    existing = worksheet.get_all_values()
    if not existing:
        worksheet.append_row(list(_SUMMARY_HEADERS), value_input_option="USER_ENTERED")

    worksheet.append_row(
        [
            week_start.isoformat(),
            member_name,
            member_text,
            facilitator_text,
        ],
        value_input_option="USER_ENTERED",
    )


def _upsert_progress_sync(
    sheet_id: str,
    *,
    member_id: int,
    week_start: date,
    member_name: str,
    tasks_text: str,
) -> None:
    spreadsheet = _open_spreadsheet(sheet_id)
    worksheet = _get_progress_worksheet(spreadsheet)
    week_key = week_start.isoformat()
    row_key = progress_row_key(member_id, week_start)
    member_norm = _normalize_member_name(member_name)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_row = [row_key, week_key, member_name.strip(), updated_at, tasks_text]

    all_rows = worksheet.get_all_values()
    matching_rows = _find_progress_row_indices(
        all_rows,
        row_key=row_key,
        week_iso=week_key,
        member_norm=member_norm,
    )

    if matching_rows:
        worksheet.update(
            f"A{matching_rows[0]}:E{matching_rows[0]}",
            [new_row],
            value_input_option="USER_ENTERED",
        )
        for idx in sorted(matching_rows[1:], reverse=True):
            worksheet.delete_rows(idx)
        return

    worksheet.append_row(new_row, value_input_option="USER_ENTERED")


async def upsert_member_progress(
    sheet_id: str | None,
    *,
    member_id: int,
    week_start: date,
    member_name: str,
    tasks_text: str,
) -> bool:
    """Снимок статусов задач на вкладку «Прогресс». False — не записали."""
    if not sheet_id:
        logger.info("No group.sheet_id — skip progress write")
        return False
    if _load_service_account_info() is None:
        logger.warning("Sheets credentials missing — skip progress write")
        return False

    lock_key = (sheet_id, week_start.isoformat(), member_id)
    lock = _upsert_locks.setdefault(lock_key, asyncio.Lock())

    loop = asyncio.get_running_loop()
    try:
        async with lock:
            await loop.run_in_executor(
                None,
                partial(
                    _upsert_progress_sync,
                    sheet_id,
                    member_id=member_id,
                    week_start=week_start,
                    member_name=member_name,
                    tasks_text=tasks_text,
                ),
            )
    except Exception:
        logger.exception("Failed to upsert progress for sheet_id=%s", sheet_id)
        return False
    return True


async def append_group_summary(
    sheet_id: str | None,
    *,
    week_start: date,
    member_name: str,
    member_text: str,
    facilitator_text: str,
) -> bool:
    """Добавить строку в групповую витрину. False — не записали (нет sheet/creds)."""
    if not sheet_id:
        logger.info("No group.sheet_id — skip Sheets write")
        return False
    if _load_service_account_info() is None:
        logger.warning("Sheets credentials missing — skip write")
        return False

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            partial(
                _append_row_sync,
                sheet_id,
                week_start=week_start,
                member_name=member_name,
                member_text=member_text,
                facilitator_text=facilitator_text,
            ),
        )
    except Exception:
        logger.exception("Failed to append summary to sheet_id=%s", sheet_id)
        return False
    return True

"""Plaud: мягкий переход на ручную вставку."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Week
from app.services.plaud import PlaudManualRequired, fetch_transcript


@pytest.mark.asyncio
async def test_fetch_transcript_uses_stored_text() -> None:
    week = Week(
        id=1,
        group_id=1,
        start_date=date.today(),
        transcript_text="  Расшифровка встречи  ",
    )
    text = await fetch_transcript(week)
    assert text == "Расшифровка встречи"


@pytest.mark.asyncio
async def test_fetch_transcript_requires_manual_when_empty() -> None:
    week = Week(id=1, group_id=1, start_date=date.today())
    with pytest.raises(PlaudManualRequired):
        await fetch_transcript(week)

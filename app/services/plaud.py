"""Забор транскрипта Plaud (§10 ТЗ).

Порядок: сохранённый текст → официальный API (если настроен) → скрейпинг URL →
мягкий запрос ручной вставки.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings
from app.db.models import Week

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


class PlaudError(Exception):
    """Базовая ошибка интеграции Plaud."""


class PlaudManualRequired(PlaudError):
    """Автозабор недоступен — нужна ручная вставка транскрипта."""


async def fetch_transcript(week: Week) -> str:
    """Получить транскрипт недели. При неудаче — PlaudManualRequired."""
    if week.transcript_text and week.transcript_text.strip():
        return week.transcript_text.strip()

    if week.plaud_url:
        if settings.plaud_api_key:
            try:
                return await _fetch_via_api(week.plaud_url)
            except PlaudError as exc:
                logger.warning("Plaud API failed for week_id=%s: %s", week.id, exc)

        try:
            return await _fetch_via_scrape(week.plaud_url)
        except PlaudError as exc:
            logger.warning("Plaud scrape failed for week_id=%s: %s", week.id, exc)

    raise PlaudManualRequired(
        "Транскрипт недоступен: нет текста, API и скрейпинг не сработали"
    )


async def _fetch_via_api(plaud_url: str) -> str:
    """Каркас официального API Plaud (настраивается через PLAUD_API_KEY)."""
    base = (settings.plaud_api_base_url or "https://api.plaud.ai").rstrip("/")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{base}/v1/transcripts/export",
            params={"url": plaud_url},
            headers={"Authorization": f"Bearer {settings.plaud_api_key}"},
        )
        if response.status_code == 404:
            raise PlaudError("Plaud API: transcript not found")
        response.raise_for_status()
        data = response.json()

    text = data.get("transcript") or data.get("text") or data.get("content")
    if not text or not str(text).strip():
        raise PlaudError("Plaud API returned empty transcript")
    return str(text).strip()


async def _fetch_via_scrape(plaud_url: str) -> str:
    """Опциональный скрейпинг публичной страницы (SPA может не отдать текст)."""
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "bot-tracker/0.1"},
    ) as client:
        response = await client.get(plaud_url)
        response.raise_for_status()
        html = response.text

    if not html.strip():
        raise PlaudError("Empty HTML from Plaud URL")

    # Грубая эвристика: если страница SPA без текста — не считаем успехом.
    plain = _TAG_RE.sub(" ", html)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) < 200:
        raise PlaudError("Plaud page looks like SPA shell without transcript text")

    return plain

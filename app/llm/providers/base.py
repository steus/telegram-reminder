"""Единый интерфейс LLM-провайдеров (§8 ТЗ)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Provider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str:
        """Вернуть текст ответа модели."""

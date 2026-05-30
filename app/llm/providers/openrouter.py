"""OpenRouter (OpenAI-compatible API)."""

from __future__ import annotations

from app.llm.providers.openai import OpenAIProvider

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    def __init__(self, *, model: str, api_key: str) -> None:
        super().__init__(model=model, api_key=api_key, base_url=_OPENROUTER_BASE)

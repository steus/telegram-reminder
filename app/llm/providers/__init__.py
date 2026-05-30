"""Фабрика LLM-провайдеров."""

from __future__ import annotations

from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.base import Provider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.openrouter import OpenRouterProvider

_SUPPORTED = frozenset({"gemini", "openai", "anthropic", "openrouter"})


def create_provider(name: str, *, model: str, api_key: str) -> Provider:
    provider = name.strip().lower()
    if provider not in _SUPPORTED:
        raise ValueError(
            f"Unknown LLM provider {name!r}. Supported: {', '.join(sorted(_SUPPORTED))}"
        )
    if not model:
        raise ValueError(f"LLM model is required for provider {provider!r}")
    if not api_key:
        raise ValueError(f"LLM API key is required for provider {provider!r}")

    if provider == "gemini":
        return GeminiProvider(model=model, api_key=api_key)
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    if provider == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    return OpenRouterProvider(model=model, api_key=api_key)

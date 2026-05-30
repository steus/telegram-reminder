"""Провайдер-агностичный LLM-клиент с фолбэком (§8 ТЗ)."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.llm.providers import create_provider
from app.llm.providers.base import Provider

logger = logging.getLogger(__name__)

# Переопределение для тестов (мок-провайдеры).
_override_primary: Provider | None = None
_override_fallback: Provider | None = None


def set_providers_for_testing(
    primary: Provider | None,
    fallback: Provider | None = None,
) -> None:
    global _override_primary, _override_fallback
    _override_primary = primary
    _override_fallback = fallback


def reset_providers_for_testing() -> None:
    set_providers_for_testing(None, None)


def _build_provider(
    provider_name: str | None,
    model: str | None,
    api_key: str | None,
) -> Provider | None:
    if not provider_name or not model or not api_key:
        return None
    return create_provider(provider_name, model=model, api_key=api_key)


def _primary_provider() -> Provider | None:
    if _override_primary is not None:
        return _override_primary
    return _build_provider(
        settings.llm_provider,
        settings.llm_model,
        settings.llm_api_key,
    )


def _fallback_provider() -> Provider | None:
    if _override_fallback is not None:
        return _override_fallback
    return _build_provider(
        settings.llm_fallback_provider,
        settings.llm_fallback_model,
        settings.llm_fallback_api_key,
    )


async def _call_provider(
    provider: Provider,
    messages: list[dict],
    *,
    json_mode: bool,
) -> str:
    return await provider.complete(messages, json_mode=json_mode)


async def ask_llm(
    messages: list[dict],
    *,
    json_mode: bool = False,
    timeout: float = 30.0,
) -> str:
    primary = _primary_provider()
    if primary is None:
        raise RuntimeError(
            "LLM is not configured: set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY"
        )

    try:
        return await asyncio.wait_for(
            _call_provider(primary, messages, json_mode=json_mode),
            timeout=timeout,
        )
    except Exception as primary_error:
        fallback = _fallback_provider()
        if fallback is None:
            raise

        logger.warning(
            "LLM primary provider failed (%s), switching to fallback",
            primary_error,
        )
        return await asyncio.wait_for(
            _call_provider(fallback, messages, json_mode=json_mode),
            timeout=timeout,
        )

"""Anthropic Messages API."""

from __future__ import annotations

import httpx

from app.llm.providers.base import Provider

_ANTHROPIC_BASE = "https://api.anthropic.com/v1"


class AnthropicProvider(Provider):
    def __init__(self, *, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str:
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_parts.append(text)
                continue
            anthropic_role = "assistant" if role == "assistant" else "user"
            anthropic_messages.append({"role": anthropic_role, "content": text})

        body: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if json_mode:
            body["system"] = (
                (body.get("system", "") + "\n\n" if body.get("system") else "")
                + "Ответь только валидным JSON."
            ).strip()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{_ANTHROPIC_BASE}/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        content_blocks = data.get("content") or []
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        if not text_parts:
            raise RuntimeError("Anthropic returned empty content")
        return "".join(text_parts)

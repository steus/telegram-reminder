"""OpenAI Chat Completions API."""

from __future__ import annotations

import httpx

from app.llm.providers.base import Provider

_OPENAI_BASE = "https://api.openai.com/v1"


class OpenAIProvider(Provider):
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = _OPENAI_BASE,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str:
        body: dict = {
            "model": self._model,
            "messages": messages,
        }
        # Формат массива задаёт промпт; response_format=json_object ломает массив строк.

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI returned no choices")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise RuntimeError("OpenAI returned empty content")
        return str(content)

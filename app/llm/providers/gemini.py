"""Google Gemini через REST API."""

from __future__ import annotations

import httpx

from app.llm.providers.base import Provider

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(Provider):
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
        contents: list[dict] = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_parts.append(text)
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        body: dict = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}

        url = f"{_GEMINI_BASE}/models/{self._model}:generateContent"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": self._api_key},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        text_parts = [p.get("text", "") for p in parts if p.get("text")]
        if not text_parts:
            raise RuntimeError("Gemini returned empty content")
        return "".join(text_parts)

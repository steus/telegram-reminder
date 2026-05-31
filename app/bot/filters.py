"""Переиспользуемые фильтры aiogram."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.services.voice import message_has_audio


class HasTextOrAudio(BaseFilter):
    """Текст (не команда) или любой поддерживаемый аудио-ввод."""

    async def __call__(self, message: Message) -> bool:
        if message.text and message.text.startswith("/"):
            return False
        return bool(message.text and message.text.strip()) or message_has_audio(message)


class HasAudioOnly(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message_has_audio(message)

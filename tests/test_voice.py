"""Голос: лимит длительности и переопределение транскрипции."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from aiogram.types import Audio, Message, VideoNote, Voice

from app.services import voice


@pytest.fixture(autouse=True)
def _reset_voice_override() -> None:
    voice.reset_transcribe_override()
    yield
    voice.reset_transcribe_override()


def test_voice_duration_ok() -> None:
    short = MagicMock(duration=60)
    long = MagicMock(duration=121)
    assert voice.duration_ok(60, max_seconds=120) is True
    assert voice.duration_ok(121, max_seconds=120) is False
    assert voice.voice_duration_ok(short, max_seconds=120) is True
    assert voice.voice_duration_ok(long, max_seconds=120) is False


def test_message_has_audio_voice_and_video_note() -> None:
    from datetime import datetime

    from aiogram.types import Chat

    chat = Chat(id=1, type="private")
    now = datetime.now()
    voice_msg = Message(
        message_id=1,
        date=now,
        chat=chat,
        voice=Voice(file_id="v", file_unique_id="vu", duration=3),
    )
    video_note_msg = Message(
        message_id=2,
        date=now,
        chat=chat,
        video_note=VideoNote(
            file_id="vn",
            file_unique_id="vnu",
            length=240,
            duration=3,
        ),
    )
    audio_msg = Message(
        message_id=3,
        date=now,
        chat=chat,
        audio=Audio(file_id="a", file_unique_id="au", duration=3),
    )
    text_msg = Message(message_id=4, date=now, chat=chat, text="hello")

    assert voice.message_has_audio(voice_msg) is True
    assert voice.message_has_audio(video_note_msg) is True
    assert voice.message_has_audio(audio_msg) is True
    assert voice.message_has_audio(text_msg) is False


def test_is_whisper_hallucination() -> None:
    assert voice.is_whisper_hallucination("С вами был Игорь Негода. (черновик)")
    assert voice.is_whisper_hallucination("  ")
    assert voice.is_whisper_hallucination("Удачи!")
    assert voice.is_whisper_hallucination("Удачи!", duration=8)
    assert not voice.is_whisper_hallucination("Сделал задачу по найму")
    assert voice.validate_transcription("Подписывайтесь на канал") is None
    assert voice.validate_transcription("Удачи!", duration=5) is None
    assert voice.validate_transcription("  готово  ") == "готово"
    assert (
        voice.validate_transcription("Сделал первую задачу, вторая в работе", duration=5)
        == "Сделал первую задачу, вторая в работе"
    )


@pytest.mark.asyncio
async def test_transcribe_file_uses_override(tmp_path: Path) -> None:
    audio = tmp_path / "test.ogg"
    audio.write_bytes(b"x")

    async def fake(audio_path: Path) -> str:
        assert audio_path == audio
        return "привет"

    voice.set_transcribe_override(fake)
    assert await voice.transcribe_file(audio) == "привет"


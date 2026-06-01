"""Голос → текст через whisper.cpp или Whisper API (§6.3–6.4, §14 ТЗ)."""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import httpx
from aiogram import Bot
from aiogram.types import Audio, Document, Message, VideoNote, Voice

from app.config import settings

logger = logging.getLogger(__name__)

# Переопределение для тестов.
_transcribe_override: (
    type[None] | object
) = None  # callable path | None sentinel

AudioKind = Literal["voice", "audio", "video_note", "document"]

VOICE_TOO_LONG = (
    "Голосовое слишком длинное — попробуй короче или напиши текстом."
)
VOICE_TRANSCRIBE_FAILED = (
    "Не получилось расшифровать аудио. Напиши текстом, пожалуйста."
)
VOICE_NOTHING_HEARD = (
    "Похоже, в записи тишина или я ничего не разобрал — "
    "напиши текстом или запиши голос ещё раз."
)
AUDIO_NOT_IN_DIALOG = (
    "Слышу аудио, но сейчас не жду его здесь. "
    "Для своих задач — /my_goals_set, для статусов — /my_goals_update."
)

# Типичные «галлюцинации» Whisper на тишине / шуме (обучающие субтитры, аутро).
_HALLUCINATION_RE = re.compile(
    r"|".join(
        (
            r"с\s+вами\s+был",
            r"подписывайтесь",
            r"спасибо\s+за\s+просмотр",
            r"продолжение\s+следует",
            r"субтитр",
            r"\(черновик\)",
            r"\bчерновик\s*$",
            r"thank\s+you\s+for\s+watching",
            r"\bsubscribe\b",
            r"amara\.org",
            r"tune2go",
            r"^\s*\.+\s*$",
        )
    ),
    re.IGNORECASE,
)

# Короткие «пустые» фразы на тишине (часто voice и video note).
_SHORT_FILLER_RE = re.compile(
    r"^("
    r"удачи"
    r"|пока"
    r"|спасибо"
    r"|благодарю"
    r"|до свидания"
    r"|всем пока"
    r"|удачи вам"
    r"|удачи всем"
    r"|хорошего дня"
    r"|хорошего вечера"
    r"|всего доброго"
    r")(?:[!.,…\s]+)?$",
    re.IGNORECASE,
)

# Слишком короткая запись без смысла — не гоняем в whisper (часто тишина).
_MIN_VOICE_SECONDS = 1
# На короткой записи односложная «галлюцинация» без контекста задач.
_SHORT_CLIP_MAX_SECONDS = 20


class EmptyTranscriptionError(Exception):
    """Пустой результат или типичная галлюцинация на тишине."""


def is_whisper_hallucination(
    text: str,
    *,
    duration: int | None = None,
) -> bool:
    normalized = " ".join(text.split())
    if not normalized:
        return True
    if _HALLUCINATION_RE.search(normalized) is not None:
        return True
    if _SHORT_FILLER_RE.match(normalized) is not None:
        return True
    if (
        duration is not None
        and duration <= _SHORT_CLIP_MAX_SECONDS
        and len(normalized) <= 40
        and _SHORT_FILLER_RE.match(normalized) is None
        and not _looks_like_task_update(normalized)
    ):
        # Очень короткий бессодержательный ответ на коротком клипе (типичный шум).
        if len(normalized.split()) <= 2 and normalized.endswith(("!", ".", "…")):
            return True
    return False


def _looks_like_task_update(text: str) -> bool:
    """Есть признаки содержательного ответа по задачам, а не случайного шума."""
    lower = text.lower()
    hints = (
        "задач",
        "сделал",
        "готов",
        "застрял",
        "затык",
        "в работе",
        "не успел",
        "не вышло",
        "недел",
        "план",
    )
    return any(h in lower for h in hints)


def validate_transcription(
    text: str,
    *,
    duration: int | None = None,
) -> str | None:
    """Вернуть очищенный текст или None, если это шум/галлюцинация."""
    cleaned = text.strip()
    if not cleaned or is_whisper_hallucination(cleaned, duration=duration):
        return None
    return cleaned


def set_transcribe_override(fn: object | None) -> None:
    global _transcribe_override
    _transcribe_override = fn


def reset_transcribe_override() -> None:
    set_transcribe_override(None)


def _document_is_audio(document: Document) -> bool:
    mime = (document.mime_type or "").lower()
    if mime.startswith("audio/"):
        return True
    if document.file_name:
        return Path(document.file_name).suffix.lower() in {
            ".mp3",
            ".ogg",
            ".oga",
            ".wav",
            ".m4a",
            ".flac",
            ".webm",
        }
    return False


def detect_audio_source(message: Message) -> tuple[AudioKind, str, int | None, str] | None:
    """Вернуть (kind, file_id, duration, suffix) или None."""
    if message.voice is not None:
        return ("voice", message.voice.file_id, message.voice.duration, ".ogg")
    if message.audio is not None:
        return (
            "audio",
            message.audio.file_id,
            message.audio.duration,
            _audio_suffix(message.audio),
        )
    if message.video_note is not None:
        return (
            "video_note",
            message.video_note.file_id,
            message.video_note.duration,
            ".mp4",
        )
    if message.document is not None and _document_is_audio(message.document):
        doc = message.document
        suffix = Path(doc.file_name or "audio.mp3").suffix or ".mp3"
        return ("document", doc.file_id, None, suffix)
    return None


def message_has_audio(message: Message) -> bool:
    return detect_audio_source(message) is not None


def duration_ok(duration: int | None, *, max_seconds: int | None = None) -> bool:
    if duration is None:
        return True
    limit = max_seconds if max_seconds is not None else settings.whisper_max_voice_duration
    return duration <= limit


def voice_duration_ok(voice: Voice, *, max_seconds: int | None = None) -> bool:
    return duration_ok(voice.duration, max_seconds=max_seconds)


async def download_telegram_file(
    bot: Bot, file_id: str, *, suffix_hint: str | None = None
) -> Path:
    tg_file = await bot.get_file(file_id)
    if tg_file.file_path is None:
        raise RuntimeError("Telegram file path is empty")

    suffix = Path(tg_file.file_path).suffix or suffix_hint or ".ogg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    await bot.download_file(tg_file.file_path, destination=tmp_path)
    return tmp_path


async def download_voice_file(bot: Bot, voice: Voice) -> Path:
    return await download_telegram_file(bot, voice.file_id)


def _audio_suffix(audio: Audio) -> str:
    if audio.file_name:
        suffix = Path(audio.file_name).suffix
        if suffix:
            return suffix
    mime = (audio.mime_type or "").lower()
    if "mpeg" in mime or mime == "audio/mp3":
        return ".mp3"
    if "ogg" in mime:
        return ".ogg"
    if "wav" in mime:
        return ".wav"
    if "m4a" in mime or "mp4" in mime:
        return ".m4a"
    return ".mp3"


def _mime_for_suffix(suffix: str) -> str:
    ext = suffix.lower()
    if ext in {".mp3", ".mpeg", ".mpga"}:
        return "audio/mpeg"
    if ext in {".ogg", ".oga"}:
        return "audio/ogg"
    if ext == ".wav":
        return "audio/wav"
    if ext in {".m4a", ".mp4"}:
        return "audio/mp4"
    if ext == ".webm":
        return "audio/webm"
    if ext == ".flac":
        return "audio/flac"
    return "application/octet-stream"


def _run_whisper_local(audio_path: Path) -> str:
    if not settings.whisper_cpp_path or not settings.whisper_model_path:
        raise RuntimeError(
            "WHISPER_CPP_PATH and WHISPER_MODEL_PATH required for WHISPER_MODE=local"
        )

    cmd = [
        settings.whisper_cpp_path,
        "-m",
        settings.whisper_model_path,
        "-f",
        str(audio_path),
        "-l",
        "ru",
        "-nt",
        "-nth",
        "0.65",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=settings.whisper_timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "whisper.cpp failed")

    text = result.stdout.strip()
    if not text:
        raise RuntimeError("whisper.cpp returned empty text")
    return text


async def _transcribe_api(audio_path: Path) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY required for WHISPER_MODE=api")

    mime = _mime_for_suffix(audio_path.suffix)
    async with httpx.AsyncClient(timeout=settings.whisper_timeout) as client:
        with audio_path.open("rb") as audio_file:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                files={"file": (audio_path.name, audio_file, mime)},
                data={"model": "whisper-1", "language": "ru"},
            )
        if response.status_code >= 400:
            logger.error("Whisper API error %s: %s", response.status_code, response.text[:500])
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("text", "")).strip()
        if not text:
            raise RuntimeError("Whisper API returned empty text")
        return text


async def transcribe_file(audio_path: Path) -> str:
    if _transcribe_override is not None:
        fn = _transcribe_override
        if asyncio.iscoroutinefunction(fn):
            return await fn(audio_path)
        return await asyncio.get_event_loop().run_in_executor(None, fn, audio_path)

    mode = settings.whisper_mode.lower()
    if mode == "api":
        return await _transcribe_api(audio_path)
    if mode == "local":
        return await asyncio.get_event_loop().run_in_executor(
            None, _run_whisper_local, audio_path
        )
    raise RuntimeError(f"Unknown WHISPER_MODE: {settings.whisper_mode}")


async def transcribe_message_audio(bot: Bot, message: Message) -> str | None:
    """Расшифровать voice / audio / video_note / audio-document. None — слишком длинное."""
    source = detect_audio_source(message)
    if source is None:
        return None

    kind, file_id, duration, suffix = source
    if not duration_ok(duration):
        return None
    if duration is not None and duration < _MIN_VOICE_SECONDS:
        raise EmptyTranscriptionError()

    audio_path: Path | None = None
    try:
        audio_path = await download_telegram_file(bot, file_id, suffix_hint=suffix)
        raw = await transcribe_file(audio_path)
        validated = validate_transcription(raw, duration=duration)
        if validated is None:
            logger.info(
                "Rejected transcription for %s (%ss): %r",
                kind,
                duration,
                raw[:80],
            )
            raise EmptyTranscriptionError()
        logger.info(
            "Transcribed %s (%ss): %d chars",
            kind,
            duration,
            len(validated),
        )
        return validated
    finally:
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


async def transcribe_voice_message(bot: Bot, message: Message) -> str | None:
    """Обратная совместимость — см. transcribe_message_audio."""
    return await transcribe_message_audio(bot, message)

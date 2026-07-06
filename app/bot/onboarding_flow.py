"""Тексты и клавиатуры шагов онбординга / настроек."""

from __future__ import annotations

import re
from datetime import time

from aiogram.types import InlineKeyboardMarkup

from app.bot import keyboards as kb
from app.bot.dialog_context import DialogContext

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_email(text: str) -> str | None:
    value = text.strip()
    if not value or not _EMAIL_RE.match(value):
        return None
    return value


def parse_phone(text: str) -> str | None:
    raw = text.strip()
    if not raw:
        return None
    has_plus = raw.startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) > 15:
        return None
    if has_plus:
        if len(digits) < 8:
            return None
        return f"+{digits}"
    if len(digits) < 7:
        return None
    return digits


def parse_checkin_time(text: str) -> time | None:
    raw = text.strip().replace(".", ":")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parts = raw.split(":")
            if len(parts) == 2:
                hour, minute = int(parts[0]), int(parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return time(hour, minute)
        except ValueError:
            continue
    return None


def parse_time_callback_data(data: str, prefix: str) -> time | None:
    """Из callback_data вида ob:tm:18:00 или st:tm:18:00."""
    head = f"{prefix}:"
    if not data.startswith(head):
        return None
    return parse_checkin_time(data[len(head) :])


def onboarding_prompt(step: str) -> tuple[str, InlineKeyboardMarkup | None]:
    prompts: dict[str, tuple[str, InlineKeyboardMarkup | None]] = {
        "input_mode": (
            "Как тебе удобнее заносить задачи на неделю?\n\n"
            "Можно подтянуть из транскрипта встречи или ввести приватно — "
            "как тебе комфортнее.",
            kb.kb_input_mode(),
        ),
        "visibility": (
            "Кому отправлять твой итог недели?\n\n"
            "Ты всегда увидишь его первым — и только после твоего «ок» "
            "он уйдёт дальше по выбранному правилу.",
            kb.kb_visibility(),
        ),
        "email": (
            "Оставь email — пригодится для связи и напоминаний вне Telegram.\n"
            "Напиши одним сообщением, например: name@example.com",
            None,
        ),
        "phone": (
            "И телефон — на случай, если в Telegram не дозвониться.\n"
            "Можно с +372 или без, например: +372 51234567 или 51234567",
            None,
        ),
        "weekday": (
            "В какой день недели тебе удобнее делать чек-ин перед встречей?",
            kb.kb_weekday(),
        ),
        "time": (
            "Во сколько напомнить о чек-ине? Можно выбрать пресет или указать своё.",
            kb.kb_time(),
        ),
        "ping": (
            "Хочешь мягкий пинг в середине недели по одной невыполненной задаче?\n"
            "Не для всех — только если тебе это помогает держать фокус.",
            kb.kb_ping(),
        ),
    }
    return prompts[step]


def settings_edit_prompt(field: str) -> tuple[str, InlineKeyboardMarkup | None]:
    mapping = {
        "im": ("Выбери способ ввода задач:", kb.kb_input_mode(prefix="st:im")),
        "vis": ("Кому отправлять итог недели?", kb.kb_visibility(prefix="st:vis")),
        "wd": ("День чек-ина:", kb.kb_weekday(prefix="st:wd")),
        "tm": (
            "Время чек-ина:",
            kb.kb_time(prefix="st:tm", custom_cb="st:tm:custom"),
        ),
        "ping": ("Пинг в середине недели:", kb.kb_ping(prefix="st:ping")),
        "email": (
            "Напиши email одним сообщением, например: name@example.com",
            kb.kb_settings_back(),
        ),
        "phone": (
            "Напиши телефон, например: +372 51234567 или 51234567",
            kb.kb_settings_back(),
        ),
    }
    text, keyboard = mapping[field]
    return text, keyboard


async def resume_onboarding_message(ctx: DialogContext) -> tuple[str, InlineKeyboardMarkup | None] | None:
    if ctx.onboarded or not ctx.step:
        return None
    return onboarding_prompt(ctx.step)

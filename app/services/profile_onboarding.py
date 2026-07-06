"""JTBD-анкета: LLM-интервью, прогресс, валидация профиля (§8A)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DialogStateEnum, Member, MemberProfile, OnboardingStatus
from app.db.repo import (
    complete_profile,
    get_or_create_profile,
    save_profile_progress,
    set_dialog_state,
    set_profile_status,
)
from app.llm.client import ask_llm
from app.llm.prompts import PROMPT_ONBOARDING_JTBD

logger = logging.getLogger(__name__)

_PROFILE_READY_MARKER = "[ПРОФИЛЬ_ГОТОВ]"
_STATE_MARKER = "[STATE]"
_PAUSE_WORDS = frozenset({"пауза", "pause"})

REQUIRED_FIELD_KEYS = (
    "niche",
    "product",
    "stage",
    "bottleneck",
    "year_goal",
    "success_criteria",
    "quarter_goal",
    "hours_per_week",
)

REQUIRED_FIELD_PATHS: dict[str, tuple[str, str]] = {
    "niche": ("business", "niche"),
    "product": ("business", "product"),
    "stage": ("business", "stage"),
    "bottleneck": ("economics", "bottleneck"),
    "year_goal": ("goals", "year_goal"),
    "success_criteria": ("goals", "success_criteria"),
    "quarter_goal": ("goals", "quarter_goal"),
    "hours_per_week": ("style", "hours_per_week"),
}

TOTAL_REQUIRED_FIELDS = len(REQUIRED_FIELD_KEYS)
TOTAL_BLOCKS = 6

SURVEY_WELCOME = (
    "Давай познакомимся поближе — короткое интервью про твой бизнес и цели "
    "(10–15 минут, можно прервать и вернуться позже).\n\n"
    "Отвечай текстом или голосом. Напиши или скажи «пауза», если нужно отложить."
)
SURVEY_RESUME = (
    "Продолжаем анкету с того места, где остановились.\n"
    "Отвечай текстом или голосом. «Пауза» — прервать и вернуться позже."
)
SURVEY_PAUSED = (
    "Ок, сохранил прогресс. Вернёшься командой /my_profile_fill, "
    "когда будет удобно."
)
SURVEY_COMPLETED = (
    "Профиль сохранён — буду учитывать его в советах и разборе задач. "
    "Обновить можно командой /my_profile_fill."
)
PROFILE_NUDGE_TEXT = (
    "Чтобы отвечать точнее под твой бизнес — стоит заполнить анкету."
)


@dataclass
class SurveyResult:
    reply_text: str
    completed: bool = False


def _load_buffer(raw: str) -> list[dict[str, str]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    result: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict) and item.get("role") and item.get("content") is not None:
            result.append({"role": str(item["role"]), "content": str(item["content"])})
    return result


def _dump_buffer(messages: list[dict[str, str]]) -> str:
    return json.dumps(messages, ensure_ascii=False)


def _load_progress(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"block": 1, "filled": []}
    if not isinstance(data, dict):
        return {"block": 1, "filled": []}
    block = data.get("block", 1)
    filled = data.get("filled", [])
    if not isinstance(filled, list):
        filled = []
    try:
        block_num = int(block)
    except (TypeError, ValueError):
        block_num = 1
    block_num = max(1, min(TOTAL_BLOCKS, block_num))
    clean_filled = [str(k) for k in filled if str(k) in REQUIRED_FIELD_KEYS]
    return {"block": block_num, "filled": clean_filled}


def _dump_progress(progress: dict[str, Any]) -> str:
    return json.dumps(progress, ensure_ascii=False)


def parse_state_marker(raw: str) -> dict[str, Any] | None:
    idx = raw.find(_STATE_MARKER)
    if idx == -1:
        return None
    rest = raw[idx + len(_STATE_MARKER) :].strip()
    brace = rest.find("{")
    if brace == -1:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(rest[brace:])
    except json.JSONDecodeError:
        logger.warning("Failed to parse [STATE] JSON near: %r", rest[brace : brace + 200])
        return None
    if not isinstance(data, dict):
        return None
    return data


def parse_profile_ready(raw: str) -> dict[str, Any] | None:
    idx = raw.find(_PROFILE_READY_MARKER)
    if idx == -1:
        return None
    rest = raw[idx + len(_PROFILE_READY_MARKER) :].strip()
    brace = rest.find("{")
    if brace == -1:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(rest[brace:])
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse [ПРОФИЛЬ_ГОТОВ] JSON near: %r", rest[brace : brace + 200]
        )
        return None
    if not isinstance(data, dict):
        return None
    return data


def strip_survey_markers(text: str) -> str:
    idx = text.find(_STATE_MARKER)
    if idx != -1:
        text = text[:idx]
    idx = text.find(_PROFILE_READY_MARKER)
    if idx != -1:
        text = text[:idx]
    return text.strip()


def _get_nested(data: dict[str, Any], section: str, key: str) -> str:
    section_data = data.get(section)
    if not isinstance(section_data, dict):
        return ""
    value = section_data.get(key, "")
    return str(value).strip() if value is not None else ""


def validate_required_fields(profile_data: dict[str, Any]) -> list[str]:
    """Вернуть список ключей обязательных полей, которые пусты."""
    missing: list[str] = []
    for field_key, (section, key) in REQUIRED_FIELD_PATHS.items():
        if not _get_nested(profile_data, section, key):
            missing.append(field_key)
    return missing


def count_filled_fields(progress: dict[str, Any]) -> int:
    filled = progress.get("filled") or []
    if not isinstance(filled, list):
        return 0
    return len([k for k in filled if k in REQUIRED_FIELD_KEYS])


def get_pending_assistant_replies(buffer: list[dict[str, str]]) -> list[str]:
    """Сообщения бота после последнего ответа пользователя — ждут ответа.

    Интервью идёт по одному ходу LLM (1–2 вопроса в сообщении). Обычно здесь
    один элемент; если накопилось несколько — показываем все.
    """
    last_user_idx = -1
    for i, item in enumerate(buffer):
        if item.get("role") == "user":
            last_user_idx = i

    start = last_user_idx + 1 if last_user_idx >= 0 else 0
    pending: list[str] = []
    for item in buffer[start:]:
        if item.get("role") != "assistant":
            continue
        content = str(item.get("content", "")).strip()
        if content:
            pending.append(content)
    return pending


def format_pending_questions_for_resume(buffer: list[dict[str, str]]) -> str | None:
    pending = get_pending_assistant_replies(buffer)
    if not pending:
        return None
    return "\n\n".join(pending)


def format_progress_line(progress: dict[str, Any]) -> str:
    filled_count = count_filled_fields(progress)
    block = progress.get("block", 1)
    try:
        block_num = int(block)
    except (TypeError, ValueError):
        block_num = 1
    block_num = max(1, min(TOTAL_BLOCKS, block_num))
    return (
        f"\n\nСобрано ключевых пунктов: {filled_count}/{TOTAL_REQUIRED_FIELDS} · "
        f"блок {block_num} из {TOTAL_BLOCKS}. "
        "Ответь текстом или голосом. «Пауза» — прервать и вернуться позже."
    )


def format_profile_display(profile_json: str) -> str:
    try:
        data = json.loads(profile_json)
    except json.JSONDecodeError:
        return "Профиль пока не заполнен."
    if not isinstance(data, dict):
        return "Профиль пока не заполнен."

    lines = ["Твой профиль:"]
    business = data.get("business") or {}
    economics = data.get("economics") or {}
    channels = data.get("channels") or {}
    goals = data.get("goals") or {}
    style = data.get("style") or {}

    field_labels: list[tuple[str, str]] = [
        ("Ниша", business.get("niche", "")),
        ("Продукт/услуга", business.get("product", "")),
        ("Клиент", business.get("customer", "")),
        ("Модель", business.get("model", "")),
        ("Стадия", business.get("stage", "")),
        ("Команда", business.get("team", "")),
        ("Выручка", economics.get("revenue_range", "")),
        ("Средний чек", economics.get("avg_check", "")),
        ("Метрики", economics.get("tracked_metrics", "")),
        ("Узкое место", economics.get("bottleneck", "")),
        ("Каналы продаж", channels.get("sales_channels", "")),
        ("CRM", channels.get("crm_tools", "")),
        ("Оплата", channels.get("payments", "")),
        ("Годовая цель", goals.get("year_goal", "")),
        ("Критерий успеха", goals.get("success_criteria", "")),
        ("Квартальная цель", goals.get("quarter_goal", "")),
        ("Часов в неделю", style.get("hours_per_week", "")),
        ("Планирование", style.get("planning_habit", "")),
        ("Нужен пинок на", style.get("needs_push_on", "")),
    ]
    for label, value in field_labels:
        if value and str(value).strip():
            lines.append(f"• {label}: {value}")

    if len(lines) == 1:
        return "Профиль пока не заполнен."
    return "\n".join(lines)


def is_pause_request(text: str) -> bool:
    return text.strip().lower() in _PAUSE_WORDS


def should_show_profile_nudge(profile: MemberProfile | None) -> bool:
    if profile is None:
        return True
    return profile.status != OnboardingStatus.completed


def _build_survey_messages(buffer: list[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": PROMPT_ONBOARDING_JTBD},
    ]
    messages.extend(buffer)
    return messages


def _merge_progress(
    current: dict[str, Any], parsed_state: dict[str, Any] | None
) -> dict[str, Any]:
    if parsed_state is None:
        return current
    block = parsed_state.get("block", current.get("block", 1))
    filled = parsed_state.get("filled", current.get("filled", []))
    try:
        block_num = int(block)
    except (TypeError, ValueError):
        block_num = current.get("block", 1)
    if not isinstance(filled, list):
        filled = current.get("filled", [])
    clean_filled = list(dict.fromkeys(str(k) for k in filled if str(k) in REQUIRED_FIELD_KEYS))
    return {"block": max(1, min(TOTAL_BLOCKS, int(block_num))), "filled": clean_filled}


async def _call_survey_llm(
    session: AsyncSession,
    member_id: int,
    buffer: list[dict[str, str]],
    progress: dict[str, Any],
) -> SurveyResult:
    messages = _build_survey_messages(buffer)
    raw = await ask_llm(messages)

    parsed_state = parse_state_marker(raw)
    progress = _merge_progress(progress, parsed_state)
    profile_data = parse_profile_ready(raw)
    reply_text = strip_survey_markers(raw) or "Расскажи подробнее."

    buffer.append({"role": "assistant", "content": reply_text})
    await save_profile_progress(session, member_id, _dump_buffer(buffer), _dump_progress(progress))

    if profile_data is not None:
        missing = validate_required_fields(profile_data)
        if not missing:
            profile_json = json.dumps(profile_data, ensure_ascii=False)
            await complete_profile(session, member_id, profile_json)
            await set_dialog_state(session, member_id, DialogStateEnum.idle)
            final = f"{reply_text}\n\n{SURVEY_COMPLETED}"
            return SurveyResult(reply_text=final, completed=True)

    reply_with_progress = f"{reply_text}{format_progress_line(progress)}"
    return SurveyResult(reply_text=reply_with_progress)


async def start_survey(
    session: AsyncSession,
    member: Member,
    *,
    resume: bool = False,
) -> str:
    profile = await get_or_create_profile(session, member.id)
    await set_profile_status(session, member.id, OnboardingStatus.in_progress)
    await set_dialog_state(session, member.id, DialogStateEnum.onboarding_survey)

    if resume and profile.onboarding_buffer and profile.onboarding_buffer != "[]":
        buffer = _load_buffer(profile.onboarding_buffer)
        progress = _load_progress(profile.progress_json)
        pending_text = format_pending_questions_for_resume(buffer)
        if pending_text:
            return f"{SURVEY_RESUME}\n\n{pending_text}{format_progress_line(progress)}"
        return f"{SURVEY_RESUME}{format_progress_line(progress)}"

    buffer: list[dict[str, str]] = []
    progress = {"block": 1, "filled": []}
    await save_profile_progress(session, member.id, "[]", _dump_progress(progress))

    buffer.append({"role": "user", "content": "Привет, готов начать интервью."})
    result = await _call_survey_llm(session, member.id, buffer, progress)
    if result.completed:
        return result.reply_text
    return f"{SURVEY_WELCOME}\n\n{result.reply_text}"


async def process_survey_message(
    session: AsyncSession,
    member: Member,
    user_text: str,
) -> SurveyResult:
    buffer = _load_buffer(
        (await get_or_create_profile(session, member.id)).onboarding_buffer
    )
    progress = _load_progress(
        (await get_or_create_profile(session, member.id)).progress_json
    )

    buffer.append({"role": "user", "content": user_text})
    return await _call_survey_llm(session, member.id, buffer, progress)


async def pause_survey(session: AsyncSession, member_id: int) -> str:
    await set_profile_status(session, member_id, OnboardingStatus.in_progress)
    await set_dialog_state(session, member_id, DialogStateEnum.idle)
    return SURVEY_PAUSED

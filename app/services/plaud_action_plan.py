"""Разбор структурированного блока «План действий» из экспорта Plaud."""

from __future__ import annotations

import re

# Латиница ↔ кириллица для частичного совпадения имён в @-заголовках
_NAME_ALIASES: dict[str, list[str]] = {
    "stepan": ["stepan", "степан"],
    "степан": ["stepan", "степан"],
    "maya": ["maya", "майя", "maia"],
    "майя": ["maya", "майя", "maia"],
    "denis": ["denis", "денис"],
    "денис": ["denis", "денис"],
}

_PLAN_TITLE_RE = re.compile(r"план\s+действий", re.IGNORECASE)
_SECTION_HEADER_RE = re.compile(r"^@(.+)$")
_TASK_LINE_RE = re.compile(r"^[-•]\s+(.+)$")
_TBD_SUFFIX_RE = re.compile(r"\s*-\s*\[TBD\]\s*$", re.IGNORECASE)
_SPEAKER_ONLY_RE = re.compile(r"^(?:speaker|спикер)\s*\d+\s*$", re.IGNORECASE)


_STOPWORDS = frozenset({"speaker", "спикер"})


def _aliases_for_name(full_name: str) -> set[str]:
    tokens = full_name.lower().split()
    aliases: set[str] = set()
    for token in tokens:
        if len(token) < 2 or token in _STOPWORDS:
            continue
        aliases.add(token)
        aliases.update(_NAME_ALIASES.get(token, []))
    return aliases


def _header_matches_member(header: str, full_name: str) -> bool:
    """Сопоставить @-заголовок Plaud с full_name участника."""
    h = header.strip().lower()
    fn = full_name.strip().lower()

    speaker_member = re.fullmatch(r"(?:speaker|спикер)\s*(\d+)", fn)
    if speaker_member:
        num = speaker_member.group(1)
        return bool(re.search(rf"(?:speaker|спикер)\s*{num}\b", h))

    if _SPEAKER_ONLY_RE.match(h):
        return False

    aliases = _aliases_for_name(full_name)
    for alias in aliases:
        if len(alias) >= 3 and alias in h:
            return True
    return False


def _clean_task_line(line: str) -> str:
    text = _TBD_SUFFIX_RE.sub("", line.strip())
    return text.strip()


def _parse_sections(plan_body: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_tasks: list[str] = []

    for raw_line in plan_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header_match = _SECTION_HEADER_RE.match(line)
        if header_match:
            if current_header is not None:
                sections.append((current_header, current_tasks))
            current_header = header_match.group(1).strip()
            current_tasks = []
            continue

        if current_header is None:
            continue

        task_match = _TASK_LINE_RE.match(line)
        if task_match:
            task = _clean_task_line(task_match.group(1))
        elif _TBD_SUFFIX_RE.search(line) or (len(line) > 8 and not line.startswith("#")):
            task = _clean_task_line(line)
        else:
            continue
        if task:
            current_tasks.append(task)

    if current_header is not None:
        sections.append((current_header, current_tasks))

    return sections


def _find_plan_body(transcript: str) -> str | None:
    """Тело плана: после «План действий» или с первого @-заголовка."""
    title = _PLAN_TITLE_RE.search(transcript)
    if title is not None:
        body = transcript[title.start() :]
        if _parse_sections(body):
            return body

    first_at = re.search(r"^@(\S.+)$", transcript, re.MULTILINE)
    if first_at is not None:
        body = transcript[first_at.start() :]
        if _parse_sections(body):
            return body

    return None


def has_action_plan_markers(transcript: str) -> bool:
    return _find_plan_body(transcript) is not None


def count_action_plan_sections(transcript: str) -> int:
    """Число @-секций в блоке «План действий»."""
    plan_body = _find_plan_body(transcript)
    if plan_body is None:
        return 0
    return len(_parse_sections(plan_body))


def extract_tasks_from_action_plan(
    transcript: str, full_name: str
) -> list[str] | None:
    """Задачи участника из блока «План действий» (@Speaker / @Имя).

    None — блока нет, вызывающий код может использовать LLM.
    list (в т.ч. пустой) — блок найден, задачи только из своей секции.
    """
    plan_body = _find_plan_body(transcript)
    if plan_body is None:
        return None

    sections = _parse_sections(plan_body)
    if not sections:
        return None

    for header, tasks in sections:
        if _header_matches_member(header, full_name):
            return tasks

    return []

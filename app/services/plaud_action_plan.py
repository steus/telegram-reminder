"""Разбор структурированного блока с @-секциями из экспорта Plaud.

Имена участников не хардкодятся: матч по токенам + транслит кириллица↔латиница.
Заголовок вроде «План действий» не обязателен — достаточно строк `@Имя`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_SECTION_HEADER_RE = re.compile(r"^@(.+)$")
_TASK_LINE_RE = re.compile(r"^[-•]\s+(.+)$")
_TBD_SUFFIX_RE = re.compile(r"\s*-\s*\[TBD\]\s*$", re.IGNORECASE)
_SPEAKER_ONLY_RE = re.compile(r"^(?:speaker|спикер)\s*\d+\s*$", re.IGNORECASE)
_CAMEL_RE = re.compile(
    r"[A-ZА-ЯЁ][a-zа-яё]+|[a-zа-яё]+|[A-ZА-ЯЁ]+(?![a-zа-яё])|\d+",
    re.UNICODE,
)
# ZWSP/BOM и др. из Docs/Plaud ломают ^@-заголовки
_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff\u00ad]")

_STOPWORDS = frozenset({"speaker", "спикер"})

# Общий транслит (не список участников). Многосимвольные замены — сначала.
_CYR_TO_LAT_MULTI = (
    ("щ", "sch"),
    ("ш", "sh"),
    ("ч", "ch"),
    ("ж", "zh"),
    ("ц", "ts"),
    ("ю", "yu"),
    ("я", "ya"),
    ("ё", "yo"),
)
_CYR_TO_LAT_SINGLE = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
}
_LAT_TO_CYR_MULTI = (
    ("sch", "щ"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("zh", "ж"),
    ("ts", "ц"),
    ("yu", "ю"),
    ("ya", "я"),
    ("yo", "ё"),
)
_LAT_TO_CYR_SINGLE = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "й",
    "z": "з",
}


def _normalize_line(raw: str) -> str:
    line = _INVISIBLE_RE.sub("", raw)
    line = line.replace("\uff20", "@")  # fullwidth ＠
    return line.strip()


def _normalize_transcript(transcript: str) -> str:
    return "\n".join(_normalize_line(line) for line in transcript.splitlines())


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яё]", text, re.IGNORECASE))


def _has_latin(text: str) -> bool:
    return bool(re.search(r"[a-z]", text, re.IGNORECASE))


def _cyr_to_lat(text: str) -> str:
    out = text.lower()
    for src, dst in _CYR_TO_LAT_MULTI:
        out = out.replace(src, dst)
    return "".join(_CYR_TO_LAT_SINGLE.get(ch, ch) for ch in out)


def _lat_to_cyr(text: str) -> str:
    out = text.lower()
    for src, dst in _LAT_TO_CYR_MULTI:
        out = out.replace(src, dst)
    return "".join(_LAT_TO_CYR_SINGLE.get(ch, ch) for ch in out)


def _script_variants(token: str) -> set[str]:
    """Токен + транслит в другую письменность (любые имена, без whitelist)."""
    variants = {token}
    if _has_cyrillic(token):
        variants.add(_cyr_to_lat(token))
    if _has_latin(token):
        variants.add(_lat_to_cyr(token))
    return {v for v in variants if len(v) >= 2}


def _tokenize(text: str) -> set[str]:
    """Токены имени/хэндла: пробелы, _, CamelCase → stepan + teus из StepanTeus."""
    tokens: set[str] = set()
    for chunk in re.split(r"[\s_\-()/]+", text.strip()):
        if not chunk:
            continue
        parts = _CAMEL_RE.findall(chunk) or [chunk]
        for part in parts:
            pl = part.lower()
            if len(pl) >= 2 and pl not in _STOPWORDS:
                tokens.update(_script_variants(pl))
        whole = re.sub(r"[^\w]", "", chunk, flags=re.UNICODE).lower()
        if len(whole) >= 2 and whole not in _STOPWORDS:
            tokens.update(_script_variants(whole))
    return tokens


def _tokens_overlap(a: set[str], b: set[str]) -> bool:
    """Совпадение токенов или префикс (denis ⊂ denisskud)."""
    if a & b:
        return True
    for left in a:
        if len(left) < 3:
            continue
        for right in b:
            if len(right) < 3:
                continue
            if left in right or right in left:
                return True
    return False


def _header_matches_member(header: str, full_name: str) -> bool:
    """Сопоставить @-заголовок Plaud с full_name участника."""
    h = header.strip()
    fn = full_name.strip()

    speaker_member = re.fullmatch(r"(?:speaker|спикер)\s*(\d+)", fn, re.IGNORECASE)
    if speaker_member:
        num = speaker_member.group(1)
        return bool(re.search(rf"(?:speaker|спикер)\s*{num}\b", h, re.IGNORECASE))

    if _SPEAKER_ONLY_RE.match(h):
        return False

    return _tokens_overlap(_tokenize(fn), _tokenize(h))


def _clean_task_line(line: str) -> str:
    text = _TBD_SUFFIX_RE.sub("", line.strip())
    return text.strip()


def _parse_sections(plan_body: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_tasks: list[str] = []

    for raw_line in plan_body.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue

        header_match = _SECTION_HEADER_RE.match(line)
        if header_match:
            if current_header is not None:
                sections.append((current_header, current_tasks))
            current_header = _normalize_line(header_match.group(1))
            current_tasks = []
            continue

        if current_header is None:
            continue

        task_match = _TASK_LINE_RE.match(line)
        if task_match:
            task = _clean_task_line(task_match.group(1))
        elif _TBD_SUFFIX_RE.search(line) or (
            len(line) >= 3 and not line.startswith("#") and not line.startswith("@")
        ):
            task = _clean_task_line(line)
        else:
            continue
        if task:
            current_tasks.append(task)

    if current_header is not None:
        sections.append((current_header, current_tasks))

    return sections


def _find_plan_body(transcript: str) -> str | None:
    """Тело плана — с первого @-заголовка (отдельный title не нужен)."""
    normalized = _normalize_transcript(transcript)
    first_at = re.search(r"^@(\S.+)$", normalized, re.MULTILINE)
    if first_at is None:
        return None
    body = normalized[first_at.start() :]
    if _parse_sections(body):
        return body
    return None


def has_action_plan_markers(transcript: str) -> bool:
    return _find_plan_body(transcript) is not None


def count_action_plan_sections(transcript: str) -> int:
    """Число @-секций в плане."""
    plan_body = _find_plan_body(transcript)
    if plan_body is None:
        return 0
    return len(_parse_sections(plan_body))


def list_action_plan_sections(transcript: str) -> list[tuple[str, list[str]]]:
    """Все @-секции: (заголовок без @, список задач)."""
    plan_body = _find_plan_body(transcript)
    if plan_body is None:
        return []
    return _parse_sections(plan_body)


def extract_tasks_for_header(transcript: str, header: str) -> list[str]:
    """Задачи секции по @-заголовку (точное или токен-совпадение)."""
    for section_header, tasks in list_action_plan_sections(transcript):
        if section_header.strip().lower() == header.strip().lower():
            return list(tasks)
        if _headers_refer_to_same_person(section_header, header):
            return list(tasks)
    return []


def rebind_action_plan_section(
    transcript: str, *, header: str, member_name: str
) -> str:
    """После ручного назначения: переименовать @-секцию под full_name участника.

    Иначе @MayaMich останется «несматченной», хотя задачи уже у Maia.
    """
    plan_body = _find_plan_body(transcript)
    if plan_body is None:
        return transcript

    sections = list(_parse_sections(plan_body))
    source_idx = next(
        (
            i
            for i, (h, _) in enumerate(sections)
            if h.strip().lower() == header.strip().lower()
            or _headers_refer_to_same_person(h, header)
        ),
        None,
    )
    if source_idx is None:
        return transcript

    _, source_tasks = sections[source_idx]
    target_idx = next(
        (
            i
            for i, (h, _) in enumerate(sections)
            if i != source_idx and _header_matches_member(h, member_name)
        ),
        None,
    )

    if target_idx is not None:
        sections[target_idx] = (member_name.strip(), source_tasks)
        sections.pop(source_idx)
    else:
        sections[source_idx] = (member_name.strip(), source_tasks)

    return "\n\n".join(
        _format_action_plan_section(h, t) for h, t in sections
    ).strip()


def list_unmatched_action_plan_headers(
    transcript: str, member_names: Iterable[str]
) -> list[str]:
    """@-заголовки, которым не нашлось участника в группе."""
    names = [n for n in member_names if n and n.strip()]
    unmatched: list[str] = []
    for header, _ in list_action_plan_sections(transcript):
        if not any(_header_matches_member(header, name) for name in names):
            unmatched.append(header)
    return unmatched


def _headers_refer_to_same_person(header_a: str, header_b: str) -> bool:
    """Считаем @Deniss и @Denis одной секцией (частичное совпадение токенов)."""
    if header_a.strip().lower() == header_b.strip().lower():
        return True
    return _tokens_overlap(_tokenize(header_a), _tokenize(header_b))


def _format_action_plan_section(header: str, tasks: list[str]) -> str:
    lines = [f"@{header}", ""]
    for task in tasks:
        if task.startswith(("-", "•")):
            lines.append(task)
        else:
            lines.append(f"- {task}")
    return "\n".join(lines)


def merge_action_plan_transcripts(existing: str | None, new_text: str) -> str:
    """Добавить или обновить @-секции в сохранённом транскрипте недели."""
    new_body = _find_plan_body(new_text) or _normalize_transcript(new_text).strip()
    new_sections = _parse_sections(new_body)
    if not new_sections:
        return (existing or "").strip() or new_text.strip()

    if not existing or not existing.strip():
        return _normalize_transcript(new_text).strip() or new_text.strip()

    existing_body = _find_plan_body(existing) or _normalize_transcript(existing).strip()
    merged: list[tuple[str, list[str]]] = list(_parse_sections(existing_body))

    for new_header, new_tasks in new_sections:
        replaced = False
        for index, (old_header, _) in enumerate(merged):
            if _headers_refer_to_same_person(old_header, new_header):
                merged[index] = (new_header, new_tasks)
                replaced = True
                break
        if not replaced:
            merged.append((new_header, new_tasks))

    return "\n\n".join(_format_action_plan_section(h, t) for h, t in merged).strip()


def replace_member_action_plan_tasks(
    transcript: str, *, member_name: str, tasks: list[str]
) -> str:
    """Обновить или добавить @-секцию участника с новым списком задач."""
    name = member_name.strip()
    clean_tasks = [t.strip() for t in tasks if t and t.strip()]
    plan_body = _find_plan_body(transcript)
    if plan_body is None:
        if not clean_tasks:
            return (transcript or "").strip()
        return _format_action_plan_section(name, clean_tasks)

    sections = list(_parse_sections(plan_body))
    idx = next(
        (i for i, (h, _) in enumerate(sections) if _header_matches_member(h, name)),
        None,
    )
    if idx is not None:
        header = sections[idx][0]
        if not clean_tasks:
            sections.pop(idx)
        else:
            sections[idx] = (header, clean_tasks)
    elif clean_tasks:
        sections.append((name, clean_tasks))

    if not sections:
        return ""
    return "\n\n".join(_format_action_plan_section(h, t) for h, t in sections).strip()


def member_has_action_plan_section(transcript: str, full_name: str) -> bool:
    """Есть ли в транскрипте @-секция для участника."""
    for header, _ in list_action_plan_sections(transcript):
        if _header_matches_member(header, full_name):
            return True
    return False


def extract_tasks_from_action_plan(
    transcript: str, full_name: str
) -> list[str] | None:
    """Задачи участника из @-секций плана.

    None — блока нет, вызывающий код может использовать LLM.
    list (в т.ч. пустой) — блок найден, задачи только из своей секции.
    """
    sections = list_action_plan_sections(transcript)
    if not sections:
        return None

    for header, tasks in sections:
        if _header_matches_member(header, full_name):
            return tasks

    return []

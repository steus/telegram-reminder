"""Вступление в группу: invite-ссылки, заявки, валидация имени."""

from __future__ import annotations

import re

INVITE_PREFIX = "join_"
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 \-'.]{0,98}$")


def parse_start_invite_code(start_args: str | None) -> str | None:
    """Из payload /start join_{code} вернуть invite_code или None."""
    if not start_args:
        return None
    payload = start_args.strip()
    if not payload.lower().startswith(INVITE_PREFIX):
        return None
    code = payload[len(INVITE_PREFIX) :].strip()
    return code or None


def validate_member_name_latin(name: str) -> bool:
    """Имя в Чате: латиница, без кириллицы, 2–100 символов."""
    cleaned = " ".join(name.split())
    if len(cleaned) < 2 or len(cleaned) > 100:
        return False
    if CYRILLIC_RE.search(cleaned):
        return False
    return LATIN_NAME_RE.match(cleaned) is not None


def normalize_member_name(name: str) -> str:
    return " ".join(name.split())


def build_invite_link(bot_username: str, invite_code: str) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?start={INVITE_PREFIX}{invite_code}"


def format_facilitator_request_message(
    *,
    full_name: str,
    group_name: str,
    telegram_username: str | None,
    chat_id: int | str,
) -> str:
    who = full_name
    if telegram_username:
        who = f"{full_name} (@{telegram_username.lstrip('@')})"
    return (
        f"Новая заявка в группу «{group_name}».\n\n"
        f"Кто: {who}\n"
        f"chat_id: {chat_id}\n\n"
        f"Имя в Чате: {full_name}"
    )


def format_members_list(
    *,
    members: list[tuple[int, str, str, bool, str | None, str | None]],
    facilitator_chat_ids: set[str],
) -> str:
    """members: (id, full_name, chat_id, is_active, email, phone)."""
    if not members:
        return "В группе пока нет активных участников."

    lines = ["Участники группы:", ""]
    for member_id, full_name, chat_id, is_active, email, phone in members:
        badges: list[str] = []
        if chat_id in facilitator_chat_ids:
            badges.append("ведущий")
        if not is_active:
            badges.append("неактивен")
        suffix = f" ({', '.join(badges)})" if badges else ""
        lines.append(f"• {full_name}{suffix} — id {member_id}")
        contact_parts: list[str] = []
        if email:
            contact_parts.append(f"email: {email}")
        if phone:
            contact_parts.append(f"тел.: {phone}")
        if contact_parts:
            lines.append(f"  {', '.join(contact_parts)}")
    return "\n".join(lines)

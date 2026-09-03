"""Приоритет вставки «Плана действий» vs личный диалог ведущего-участника."""

from __future__ import annotations

from app.bot.dialog_context import DialogContext
from app.services.plaud_action_plan import has_action_plan_markers


def facilitator_paste_takes_priority(ctx: DialogContext, text: str) -> bool:
    """True — сообщение ведущего должно идти в paste-поток, не в анкету/прочее."""
    return ctx.is_facilitator_pasting() or has_action_plan_markers(text)

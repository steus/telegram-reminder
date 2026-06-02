"""Ручная правка шагов декомпозиции без LLM."""

from app.bot.dialog_context import DialogContext
from app.services.decompose import _lines_to_steps


def test_manual_steps_preserve_user_wording() -> None:
    text = "1. Позвонить клиенту\n2. Согласовать дедлайн"
    assert _lines_to_steps(text) == [
        "Позвонить клиенту",
        "Согласовать дедлайн",
    ]


def test_decompose_awaiting_edit_flag_roundtrip() -> None:
    ctx = DialogContext(decompose_task_id=1, decompose_steps=["шаг"])
    ctx.start_decompose_edit()
    raw = ctx.to_json()
    restored = DialogContext.from_json(raw)
    assert restored.decompose_awaiting_edit is True
    restored.set_decompose_steps(["новый шаг"])
    assert restored.decompose_awaiting_edit is False

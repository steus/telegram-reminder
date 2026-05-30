"""Сохранение режима вставки транскрипта в dialog_context."""

from app.bot.dialog_context import DialogContext


def test_facilitator_paste_roundtrip() -> None:
    ctx = DialogContext(onboarded=True)
    ctx.start_facilitator_paste(group_id=1)
    assert ctx.is_facilitator_pasting()
    assert ctx.facilitator_pending == ""

    ctx.append_facilitator_paste("@Speaker 1\n- task one")
    assert "@Speaker 1" in (ctx.facilitator_pending or "")
    ctx.append_facilitator_paste("@Степан\n- task two")
    assert "task two" in (ctx.facilitator_pending or "")

    raw = ctx.to_json()
    restored = DialogContext.from_json(raw)
    assert restored.facilitator_group_id == 1
    assert "task one" in (restored.facilitator_pending or "")
    assert "task two" in (restored.facilitator_pending or "")

    restored.clear_facilitator_paste()
    assert not restored.is_facilitator_pasting()
    assert restored.facilitator_pending is None


def test_facilitator_paste_survives_other_fields() -> None:
    ctx = DialogContext(onboarded=True, settings_field="im")
    ctx.start_facilitator_paste(42)
    ctx.append_facilitator_paste("chunk")
    restored = DialogContext.from_json(ctx.to_json())
    assert restored.settings_field == "im"
    assert restored.facilitator_group_id == 42

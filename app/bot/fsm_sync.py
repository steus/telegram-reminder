"""Синхронизация aiogram FSM с dialog_state в БД (§7 ТЗ)."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext

from app.bot.dialog_context import DialogContext
from app.instance_config import get_onboarding_steps
from app.bot.states import OnboardingStates, SettingsStates


async def sync_fsm_from_context(state: FSMContext, ctx: DialogContext) -> None:
    if ctx.settings_field:
        contact_mapping = {
            "email": SettingsStates.email,
            "phone": SettingsStates.phone,
        }
        contact_state = contact_mapping.get(ctx.settings_field)
        if contact_state is not None:
            await state.set_state(contact_state)
            return
        await state.set_state(SettingsStates.editing)
        return
    if not ctx.onboarded and ctx.step:
        mapping = {
            "input_mode": OnboardingStates.input_mode,
            "visibility": OnboardingStates.visibility,
            "email": OnboardingStates.email,
            "phone": OnboardingStates.phone,
            "weekday": OnboardingStates.weekday,
            "time": OnboardingStates.time,
            "ping": OnboardingStates.ping,
        }
        fsm_state = mapping.get(ctx.step)
        if fsm_state:
            await state.set_state(fsm_state)
        return
    await state.clear()


def next_onboarding_step(current: str | None) -> str:
    steps = get_onboarding_steps()
    if not steps:
        return "input_mode"
    if current is None:
        return steps[0]
    try:
        idx = steps.index(current)
    except ValueError:
        return steps[0]
    return steps[min(idx + 1, len(steps) - 1)]

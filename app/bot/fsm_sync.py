"""Синхронизация aiogram FSM с dialog_state в БД (§7 ТЗ)."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext

from app.bot.dialog_context import DialogContext, ONBOARDING_STEPS
from app.bot.states import OnboardingStates, SettingsStates


async def sync_fsm_from_context(state: FSMContext, ctx: DialogContext) -> None:
    if ctx.settings_field:
        await state.set_state(SettingsStates.editing)
        return
    if not ctx.onboarded and ctx.step:
        mapping = {
            "input_mode": OnboardingStates.input_mode,
            "visibility": OnboardingStates.visibility,
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
    if current is None:
        return ONBOARDING_STEPS[0]
    idx = ONBOARDING_STEPS.index(current)
    return ONBOARDING_STEPS[min(idx + 1, len(ONBOARDING_STEPS) - 1)]

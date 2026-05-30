"""FSM-состояния aiogram, синхронизируемые с dialog_state.context_json (§7 ТЗ)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    input_mode = State()
    visibility = State()
    weekday = State()
    time = State()
    custom_time = State()
    ping = State()


class SettingsStates(StatesGroup):
    menu = State()
    editing = State()
    custom_time = State()

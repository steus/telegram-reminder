"""Сериализация dialog_state.context_json — источник правды для онбординга/настроек."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


ONBOARDING_STEPS = ("input_mode", "visibility", "weekday", "time", "ping")


@dataclass
class DialogContext:
    onboarded: bool = False
    step: str | None = None
    settings_field: str | None = None
    task_step: str | None = None  # collect | confirm | correct

    @classmethod
    def from_json(cls, raw: str | None) -> DialogContext:
        if not raw:
            return cls()
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            return cls()
        return cls(
            onboarded=bool(data.get("onboarded", False)),
            step=data.get("step"),
            settings_field=data.get("settings_field"),
            task_step=data.get("task_step"),
        )

    def to_json(self) -> str:
        payload = {k: v for k, v in asdict(self).items() if v is not None}
        if not self.onboarded:
            payload.setdefault("onboarded", False)
        return json.dumps(payload, ensure_ascii=False)

    def start_onboarding(self) -> None:
        self.onboarded = False
        self.step = ONBOARDING_STEPS[0]
        self.settings_field = None

    def advance_onboarding(self) -> bool:
        """Перейти к следующему шагу. True — онбординг завершён."""
        if self.step is None:
            self.start_onboarding()
            return False
        try:
            idx = ONBOARDING_STEPS.index(self.step)
        except ValueError:
            self.step = ONBOARDING_STEPS[0]
            return False
        if idx + 1 >= len(ONBOARDING_STEPS):
            self.onboarded = True
            self.step = None
            return True
        self.step = ONBOARDING_STEPS[idx + 1]
        return False

    def begin_settings_edit(self, field: str) -> None:
        self.settings_field = field

    def clear_settings_edit(self) -> None:
        self.settings_field = None

    def start_task_collection(self) -> None:
        self.task_step = "collect"

    def show_task_confirmation(self) -> None:
        self.task_step = "confirm"

    def start_task_correction(self) -> None:
        self.task_step = "correct"

    def clear_task_flow(self) -> None:
        self.task_step = None

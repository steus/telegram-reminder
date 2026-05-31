"""Сериализация dialog_state.context_json — источник правды для онбординга/настроек."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


ONBOARDING_STEPS = ("input_mode", "visibility", "weekday", "time", "ping")
MAX_CHECKIN_MESSAGES = 10


@dataclass
class DialogContext:
    onboarded: bool = False
    step: str | None = None
    settings_field: str | None = None
    task_step: str | None = None  # collect | confirm | correct
    facilitator_group_id: int | None = None
    facilitator_pending: str | None = None
    checkin_messages: list[dict[str, str]] | None = None
    decompose_task_id: int | None = None
    decompose_steps: list[str] | None = None
    pending_summary_week_id: int | None = None
    pending_summary_member_text: str | None = None
    pending_summary_facilitator_text: str | None = None

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
            facilitator_group_id=data.get("facilitator_group_id"),
            facilitator_pending=data.get("facilitator_pending"),
            checkin_messages=_parse_message_list(data.get("checkin_messages")),
            decompose_task_id=data.get("decompose_task_id"),
            decompose_steps=_parse_str_list(data.get("decompose_steps")),
            pending_summary_week_id=data.get("pending_summary_week_id"),
            pending_summary_member_text=data.get("pending_summary_member_text"),
            pending_summary_facilitator_text=data.get("pending_summary_facilitator_text"),
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
        self.decompose_task_id = None
        self.decompose_steps = None

    def show_task_confirmation(self) -> None:
        self.task_step = "confirm"

    def start_task_correction(self) -> None:
        self.task_step = "correct"

    def clear_task_flow(self) -> None:
        self.task_step = None

    def start_facilitator_paste(self, group_id: int) -> None:
        self.facilitator_group_id = group_id
        self.facilitator_pending = ""

    def append_facilitator_paste(self, chunk: str) -> str:
        chunk = chunk.strip()
        if self.facilitator_pending:
            self.facilitator_pending = f"{self.facilitator_pending}\n\n{chunk}"
        else:
            self.facilitator_pending = chunk
        return self.facilitator_pending

    def clear_facilitator_paste(self) -> None:
        self.facilitator_group_id = None
        self.facilitator_pending = None

    def is_facilitator_pasting(self) -> bool:
        return self.facilitator_group_id is not None

    def append_checkin_message(self, role: str, content: str) -> None:
        messages = list(self.checkin_messages or [])
        messages.append({"role": role, "content": content.strip()})
        if len(messages) > MAX_CHECKIN_MESSAGES:
            messages = messages[-MAX_CHECKIN_MESSAGES:]
        self.checkin_messages = messages

    def clear_checkin_messages(self) -> None:
        self.checkin_messages = None

    def start_decompose(self, task_id: int, steps: list[str] | None = None) -> None:
        self.decompose_task_id = task_id
        self.decompose_steps = steps

    def set_decompose_steps(self, steps: list[str]) -> None:
        self.decompose_steps = steps

    def clear_decompose(self) -> None:
        self.decompose_task_id = None
        self.decompose_steps = None

    def set_pending_summary(
        self,
        *,
        week_id: int,
        member_text: str,
        facilitator_text: str,
    ) -> None:
        self.pending_summary_week_id = week_id
        self.pending_summary_member_text = member_text
        self.pending_summary_facilitator_text = facilitator_text

    def clear_pending_summary(self) -> None:
        self.pending_summary_week_id = None
        self.pending_summary_member_text = None
        self.pending_summary_facilitator_text = None

    def has_pending_summary(self) -> bool:
        return self.pending_summary_week_id is not None


def _parse_message_list(raw: object) -> list[dict[str, str]] | None:
    if not isinstance(raw, list):
        return None
    result: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("role") and item.get("content"):
            result.append({"role": str(item["role"]), "content": str(item["content"])})
    return result or None


def _parse_str_list(raw: object) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    return [str(x) for x in raw if str(x).strip()] or None

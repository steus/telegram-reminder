"""Инлайн-клавиатуры для онбординга и настроек."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import InputMode, Member, Task, TaskStatus, Visibility

# Статусы чек-ина (§6.4): callback_data = t:{task_id}:{status}, ≤64 байт
CHECKIN_STATUS_BUTTONS: tuple[tuple[TaskStatus, str, str], ...] = (
    (TaskStatus.done, "✅", "Сделал"),
    (TaskStatus.in_progress, "🔄", "В работе"),
    (TaskStatus.stuck, "⛔", "Затык"),
)


def checkin_callback_data(task_id: int, status: TaskStatus) -> str:
    return f"t:{task_id}:{status.value}"


def _checkin_button_label(
    icon: str, label: str, status: TaskStatus, selected: TaskStatus | None
) -> str:
    if selected == status:
        return f"• {icon} {label}"
    return f"{icon} {label}"


def kb_checkin_task_row(task: Task) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=_checkin_button_label(icon, label, status, task.status),
            callback_data=checkin_callback_data(task.id, status),
        )
        for status, icon, label in CHECKIN_STATUS_BUTTONS
    ]


def kb_checkin_message(tasks: list[Task]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[kb_checkin_task_row(task) for task in tasks]
    )


def decompose_offer_callback(task_id: int, accept: bool) -> str:
    return f"dc:yn:{'yes' if accept else 'no'}:{task_id}"


def kb_decompose_offer(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, помоги",
                    callback_data=decompose_offer_callback(task_id, True),
                ),
                InlineKeyboardButton(
                    text="Нет, спасибо",
                    callback_data=decompose_offer_callback(task_id, False),
                ),
            ]
        ]
    )


def kb_decompose_confirm(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Всё верно",
                    callback_data=f"dc:ok:{task_id}",
                ),
                InlineKeyboardButton(
                    text="✏️ Поправить",
                    callback_data=f"dc:ed:{task_id}",
                ),
            ]
        ]
    )

WEEKDAYS = (
    (0, "Пн"),
    (1, "Вт"),
    (2, "Ср"),
    (3, "Чт"),
    (4, "Пт"),
    (5, "Сб"),
    (6, "Вс"),
)

TIME_PRESETS = ("09:00", "12:00", "18:00", "20:00")

INPUT_MODE_LABELS = {
    InputMode.auto: "Из транскрипта встречи",
    InputMode.private: "Приватно, напрямую боту",
}

VISIBILITY_LABELS = {
    Visibility.group: "Группе",
    Visibility.facilitator: "Только ведущему",
    Visibility.private: "Только мне",
}


def kb_input_mode(prefix: str = "ob:im") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=INPUT_MODE_LABELS[InputMode.auto],
                    callback_data=f"{prefix}:auto",
                )
            ],
            [
                InlineKeyboardButton(
                    text=INPUT_MODE_LABELS[InputMode.private],
                    callback_data=f"{prefix}:private",
                )
            ],
        ]
    )


def kb_visibility(prefix: str = "ob:vis") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=VISIBILITY_LABELS[Visibility.group],
                    callback_data=f"{prefix}:group",
                )
            ],
            [
                InlineKeyboardButton(
                    text=VISIBILITY_LABELS[Visibility.facilitator],
                    callback_data=f"{prefix}:facilitator",
                )
            ],
            [
                InlineKeyboardButton(
                    text=VISIBILITY_LABELS[Visibility.private],
                    callback_data=f"{prefix}:private",
                )
            ],
        ]
    )


def kb_weekday(prefix: str = "ob:wd") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, label in WEEKDAYS:
        row.append(
            InlineKeyboardButton(text=label, callback_data=f"{prefix}:{idx}")
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_time(prefix: str = "ob:tm", custom_cb: str = "ob:tm:custom") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for t in TIME_PRESETS:
        row.append(InlineKeyboardButton(text=t, callback_data=f"{prefix}:{t}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(text="✏️ Другое время", callback_data=custom_cb)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_ping(prefix: str = "ob:ping") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, напоминать", callback_data=f"{prefix}:1"),
                InlineKeyboardButton(text="Нет, спасибо", callback_data=f"{prefix}:0"),
            ]
        ]
    )


def kb_settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Способ ввода задач", callback_data="st:ed:im")],
            [InlineKeyboardButton(text="Видимость итога", callback_data="st:ed:vis")],
            [InlineKeyboardButton(text="День чек-ина", callback_data="st:ed:wd")],
            [InlineKeyboardButton(text="Время чек-ина", callback_data="st:ed:tm")],
            [InlineKeyboardButton(text="Пинг в середине недели", callback_data="st:ed:ping")],
        ]
    )


def kb_settings_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад в настройки", callback_data="st:menu")]
        ]
    )


def format_member_settings(member: Member) -> str:
    wd = dict(WEEKDAYS).get(member.checkin_weekday, str(member.checkin_weekday))
    tm = member.checkin_time.strftime("%H:%M")
    ping = "да" if member.midweek_ping else "нет"
    return (
        f"• Способ ввода: {INPUT_MODE_LABELS[member.input_mode]}\n"
        f"• Видимость итога: {VISIBILITY_LABELS[member.visibility]}\n"
        f"• Чек-ин: {wd}, {tm} ({member.timezone})\n"
        f"• Пинг в середине недели: {ping}"
    )

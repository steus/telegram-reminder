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


def summary_send_callback(accept: bool) -> str:
    return f"sm:yn:{'yes' if accept else 'no'}"


def kb_summary_send() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отправить",
                    callback_data=summary_send_callback(True),
                ),
                InlineKeyboardButton(
                    text="Нет, оставить у себя",
                    callback_data=summary_send_callback(False),
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


def kb_membership_join_confirm(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, хочу вступить",
                    callback_data=f"mj:join:yes:{group_id}",
                ),
                InlineKeyboardButton(
                    text="Нет",
                    callback_data=f"mj:join:no:{group_id}",
                ),
            ]
        ]
    )


def kb_membership_request_decision(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=f"mj:ok:{request_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"mj:no:{request_id}",
                ),
            ]
        ]
    )


def kb_member_admin_actions(
    member_id: int, *, is_facilitator: bool, is_active: bool
) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if is_active and not is_facilitator:
        buttons.append(
            InlineKeyboardButton(
                text="Сделать ведущим",
                callback_data=f"mj:fac:{member_id}",
            )
        )
    if is_active:
        buttons.append(
            InlineKeyboardButton(
                text="Деактивировать",
                callback_data=f"mj:deact:{member_id}",
            )
        )
    buttons.append(
        InlineKeyboardButton(
            text="Удалить",
            callback_data=f"mj:del:{member_id}",
        )
    )
    return buttons


def kb_member_delete_confirm(member_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data=f"mj:del:ok:{member_id}",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"mj:del:cn:{member_id}",
                ),
            ]
        ]
    )


def kb_goals_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Задать задачи", callback_data="gl:act:set")],
            [InlineKeyboardButton(text="Задачи и статусы", callback_data="gl:act:view")],
            [InlineKeyboardButton(text="Обновить статус", callback_data="gl:act:update")],
            [InlineKeyboardButton(text="Прогресс по неделям", callback_data="gl:act:stats")],
            [InlineKeyboardButton(text="Обновить в таблице", callback_data="gl:act:submit")],
        ]
    )


def kb_group_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Участники и заявки", callback_data="fc:m:members")],
            [InlineKeyboardButton(text="🎯 Задачи группы", callback_data="fc:m:goals")],
            [InlineKeyboardButton(text="📝 Транскрипт (Plaud)", callback_data="fc:m:transcript")],
        ]
    )


def kb_group_members_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ссылка-приглашение", callback_data="fc:act:invite")],
            [InlineKeyboardButton(text="Участники и ведущие", callback_data="fc:act:members")],
            [InlineKeyboardButton(text="Заявки на вступление", callback_data="fc:act:requests")],
            [InlineKeyboardButton(text="← Назад", callback_data="fc:m:root")],
        ]
    )


def kb_group_goals_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Задачи и статусы группы", callback_data="fc:act:goals_view")],
            [InlineKeyboardButton(text="Обновить задачи в таблице", callback_data="fc:act:goals_sync")],
            [InlineKeyboardButton(text="← Назад", callback_data="fc:m:root")],
        ]
    )


def kb_group_transcript_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Вставить «План действий»", callback_data="fc:act:paste")],
            [InlineKeyboardButton(text="Завершить вставку", callback_data="fc:act:paste_done")],
            [InlineKeyboardButton(text="Ссылка на Plaud", callback_data="fc:act:plaud")],
            [InlineKeyboardButton(text="← Назад", callback_data="fc:m:root")],
        ]
    )


def kb_group_members(
    members: list[Member], facilitator_chat_ids: set[str]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for member in members:
        row = kb_member_admin_actions(
            member.id,
            is_facilitator=member.telegram_chat_id in facilitator_chat_ids,
            is_active=member.is_active,
        )
        if row:
            rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows or [[]])


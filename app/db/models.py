"""SQLAlchemy-модели (§5 ТЗ).

Этап 0: только `group` и `member` (+ их enum). Остальные таблицы (week, task,
dialog_state, summary) добавляются на последующих этапах.

Enum хранятся как VARCHAR (native_enum=False) — переносимо между SQLite и
Postgres без специфичных типов.
"""

from __future__ import annotations

import enum
from datetime import time

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class InputMode(str, enum.Enum):
    """Как задачи попадают в систему (вход)."""

    auto = "auto"
    private = "private"


class Visibility(str, enum.Enum):
    """Кому уходит итог недели (видимость)."""

    group = "group"
    facilitator = "facilitator"
    private = "private"


class Group(Base):
    __tablename__ = "group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    facilitator_chat_id: Mapped[str] = mapped_column(String(64))
    sheet_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    members: Mapped[list["Member"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Member(Base):
    __tablename__ = "member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"))
    full_name: Mapped[str] = mapped_column(String(255))
    telegram_chat_id: Mapped[str] = mapped_column(String(64), unique=True)

    input_mode: Mapped[InputMode] = mapped_column(
        Enum(InputMode, native_enum=False, length=16),
        default=InputMode.private,
    )
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, native_enum=False, length=16),
        default=Visibility.private,
    )

    checkin_weekday: Mapped[int] = mapped_column(Integer, default=4)  # 0=Mon..6=Sun
    checkin_time: Mapped[time] = mapped_column(Time, default=time(18, 0))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Tallinn")
    midweek_ping: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    group: Mapped["Group"] = relationship(back_populates="members")

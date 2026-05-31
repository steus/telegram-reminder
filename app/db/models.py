"""SQLAlchemy-модели (§5 ТЗ).

Enum хранятся как VARCHAR (native_enum=False) — переносимо между SQLite и
Postgres без специфичных типов.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


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


class SharedScope(str, enum.Enum):
    """Куда фактически ушла сводка (§5 ТЗ)."""

    group = "group"
    facilitator = "facilitator"
    private = "private"
    none = "none"


class DialogStateEnum(str, enum.Enum):
    """Где участник в диалоге (§5 ТЗ)."""

    idle = "idle"
    confirming_tasks = "confirming_tasks"
    checkin = "checkin"
    decomposing = "decomposing"


class TaskSource(str, enum.Enum):
    plaud = "plaud"
    manual = "manual"
    decomposed = "decomposed"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    in_progress = "in_progress"
    stuck = "stuck"
    decomposed = "decomposed"


class Group(Base):
    __tablename__ = "group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    facilitator_chat_id: Mapped[str] = mapped_column(String(64))
    sheet_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    members: Mapped[list["Member"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    weeks: Mapped[list["Week"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    facilitators: Mapped[list["GroupFacilitator"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupFacilitator(Base):
    """Ведущие группы — один или несколько chat_id на группу."""

    __tablename__ = "group_facilitator"
    __table_args__ = (
        UniqueConstraint("group_id", "telegram_chat_id", name="uq_group_facilitator"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"))
    telegram_chat_id: Mapped[str] = mapped_column(String(64))

    group: Mapped["Group"] = relationship(back_populates="facilitators")


class Week(Base):
    __tablename__ = "week"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"))
    start_date: Mapped[date] = mapped_column(Date)
    plaud_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    group: Mapped["Group"] = relationship(back_populates="weeks")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="week", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("member.id"))
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id"))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[TaskSource] = mapped_column(
        Enum(TaskSource, native_enum=False, length=16),
        default=TaskSource.manual,
    )
    parent_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("task.id"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=16),
        default=TaskStatus.pending,
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    member: Mapped["Member"] = relationship(back_populates="tasks")
    week: Mapped["Week"] = relationship(back_populates="tasks")
    parent_task: Mapped["Task | None"] = relationship(remote_side="Task.id")


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
    dialog_state: Mapped["DialogState | None"] = relationship(
        back_populates="member", uselist=False, cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="member")
    summaries: Mapped[list["Summary"]] = relationship(back_populates="member")


class Summary(Base):
    __tablename__ = "summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("member.id"))
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id"))
    member_text: Mapped[str] = mapped_column(Text)
    facilitator_text: Mapped[str] = mapped_column(Text)
    shared_scope: Mapped[SharedScope] = mapped_column(
        Enum(SharedScope, native_enum=False, length=16),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    member: Mapped["Member"] = relationship(back_populates="summaries")
    week: Mapped["Week"] = relationship()


class DialogState(Base):
    __tablename__ = "dialog_state"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id"), primary_key=True
    )
    state: Mapped[DialogStateEnum] = mapped_column(
        Enum(DialogStateEnum, native_enum=False, length=32),
        default=DialogStateEnum.idle,
    )
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    active_week_id: Mapped[int | None] = mapped_column(
        ForeignKey("week.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    member: Mapped["Member"] = relationship(back_populates="dialog_state")

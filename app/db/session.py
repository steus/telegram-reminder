"""Async-движок и фабрика сессий SQLAlchemy.

Строка подключения берётся из настроек (DATABASE_URL). Смена на Postgres —
это смена строки подключения, без правок бизнес-логики (§3 ТЗ).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


def _engine_connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        # Ждём освобождения файла (DB Browser, второй процесс и т.д.)
        return {"timeout": 30}
    return {}


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args=_engine_connect_args(settings.database_url),
)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception:
            # Файл только для чтения или нет прав на WAL — работаем в текущем режиме.
            pass
        cursor.close()

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Контекст-менеджер сессии с авто-commit/rollback."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

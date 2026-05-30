# bot-tracker

Telegram-бот для недельного peer-accountability трекинга задач бизнес-группы.
Тон бота — поддерживающий напарник, а не контролёр. Полное ТЗ — в
[`TZ_bot_tracker.md`](./TZ_bot_tracker.md), план сборки по этапам — в [`plan/`](./plan).

Текущий статус: **этап 1 — онбординг и настройки** (`/start`, `/settings`,
кнопочный онбординг, `dialog_state`, seed-скрипт).

## Стек

Python 3.12+, aiogram 3.x, SQLAlchemy 2.x (async) + aiosqlite, Alembic,
APScheduler, pydantic-settings. Один процесс: бот + планировщик в общем event loop.

## Запуск локально

### Вариант A — Docker (рекомендуется)

```bash
cp .env.example .env          # вписать TELEGRAM_BOT_TOKEN тестового бота
docker compose up --build
```

Миграции применяются автоматически на старте контейнера. БД лежит в `./data/app.db`.

### Вариант B — venv

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # вписать TELEGRAM_BOT_TOKEN
alembic upgrade head
python -m app.main
```

## Тестовый участник (этап 1)

Узнай свой Telegram chat_id (например, через [@userinfobot](https://t.me/userinfobot))
и создай запись в БД:

```bash
python scripts/seed_member.py --chat-id ВАШ_CHAT_ID --name "Ваше Имя"
```

Затем отправь боту `/start` — пройди онбординг кнопками. Незнакомый chat_id
получит вежливый отказ без создания записи.

## Полезное

```bash
# Новая миграция после правки моделей
alembic revision --autogenerate -m "описание"
alembic upgrade head

# Проверить таблицы в SQLite
python -c "import sqlite3; print(sqlite3.connect('data/app.db').execute(\
  'select name from sqlite_master where type=\"table\"').fetchall())"
```

## Деплой на VPS

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Подробности (systemd-альтернатива, бэкапы) — на этапе 7 плана.

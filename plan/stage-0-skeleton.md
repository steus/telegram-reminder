# Этап 0 — Каркас и инфраструктура

> Сначала прочитай `plan/CONVENTIONS.md`. Затем — только разделы ТЗ ниже.

## Цель

Поднять рабочий каркас проекта: структура, конфиг, БД с моделями `group` и
`member`, Alembic, Docker-окружение. Бот запускается (long polling) и отвечает
на `/start` заглушкой. Это база для всех следующих этапов.

## Читать в ТЗ

- §3 (стек), §4 (архитектура), §5 — только таблицы `group` и `member`,
  §12 (`.env`), §13 (структура), §14 (деплой — для понимания цели).

## Предусловия

- Пустой репозиторий (есть только `TZ_bot_tracker.md` и `plan/`).

## Задачи

1. **Инициализация проекта**
   - `git init`, `.gitignore` (Python, `.env`, `data/`, `.venv`, `__pycache__`).
   - `pyproject.toml`: метаданные + базовые зависимости (см. CONVENTIONS, набор
     этапа 0). Пакет `app` устанавливается editable.
2. **Конфиг** (`app/config.py`)
   - `pydantic-settings`: класс `Settings` с полями из §12, читает `.env`.
   - На этапе 0 обязательны: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`,
     `DEFAULT_TIMEZONE`. Остальные поля — опциональные (заглушки), чтобы не падать.
   - Синглтон `settings = Settings()`.
3. **Слой БД**
   - `app/db/session.py`: async engine + `async_sessionmaker` из `DATABASE_URL`.
   - `app/db/models.py`: `Base` (DeclarativeBase) + модели `group` и `member`
     строго по §5 (включая enum `input_mode`, `visibility`; поля чек-ина, tz,
     `midweek_ping`, `is_active`). Enum — через `sqlalchemy.Enum` (переносимо на Postgres).
   - `app/db/repo.py`: заготовки `get_member_by_chat_id`, `get_or_none` — минимум
     для `/start`.
4. **Alembic**
   - Инициализировать, настроить `env.py` на async-движок и `Base.metadata`.
   - Первая миграция (autogenerate) для `group` + `member`.
5. **Бот-каркас**
   - `app/bot/routers/common.py`: роутер с хендлером `/start`, который пока просто
     отвечает «Привет! Я бот-трекер. Онбординг появится на следующем шаге.»
     (тон — напарник). Плюс `/help` со списком будущих команд.
   - `app/main.py`: создать `Bot`/`Dispatcher`, подключить роутер `common`,
     создать (пустой пока) `AsyncIOScheduler` и запустить polling в одном event loop.
     Предусмотреть аккуратное завершение (graceful shutdown).
6. **Docker**
   - `Dockerfile` (python:3.12-slim, установка пакета, не-root юзер).
   - `entrypoint.sh`: `alembic upgrade head` → `python -m app.main`.
   - `docker-compose.yml`: сервис `bot`, том на `./data`, env из `.env`.
   - `docker-compose.prod.yml`: оверрайд для прода (restart: always, без bind-mount
     исходников) — пока минимальный, детально допилим на этапе 7.
7. **Конфиги среды**
   - `.env.example` со всеми ключами из §12 и комментариями.
   - `README.md`: краткое «как запустить локально» (Docker и venv).

## Создаются/меняются файлы

`pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `Dockerfile`,
`entrypoint.sh`, `docker-compose.yml`, `docker-compose.prod.yml`,
`app/__init__.py`, `app/config.py`, `app/main.py`,
`app/db/{__init__,session,models,repo}.py`,
`app/bot/__init__.py`, `app/bot/routers/{__init__,common}.py`,
`alembic.ini`, `alembic/env.py`, `alembic/versions/*_init.py`.

## Definition of Done

- `docker compose up --build` поднимает контейнер без ошибок; миграции применяются.
- В Telegram бот (тестовый токен) отвечает на `/start` и `/help`.
- `app.db` создаётся в `./data`, в нём есть таблицы `group` и `member`.
- Альтернативный запуск через venv тоже работает.

## Локальная проверка

1. Создать тестового бота у @BotFather, токен в `.env`.
2. `docker compose up --build`.
3. Написать боту `/start` → получить приветствие.
4. Проверить таблицы:
   `docker compose exec bot python -c "import sqlite3; print(sqlite3.connect('data/app.db').execute('select name from sqlite_master where type=\"table\"').fetchall())"`.

## Заметка для следующего этапа

Запиши в `PROGRESS.md`: как локально завести тестового участника (нужно будет
руками вставить `group` и затем участники появляются через онбординг — об этом
этап 1).

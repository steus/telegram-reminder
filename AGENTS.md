# AGENTS.md — карта проекта для агента

Читай **этот файл первым**. Он даёт минимум контекста и говорит, **куда смотреть**
за деталями, чтобы не загружать в контекст все документы сразу.

## Что это

`bot-tracker` — Telegram-бот недельного peer-accountability трекинга задач бизнес-группы.
Тон бота — поддерживающий **напарник**, не контролёр. Все 7 этапов сборки завершены
(см. `plan/PROGRESS.md`), проект в рабочем состоянии.

## Стек

Python 3.12+, `aiogram` 3.x (async, long polling), `SQLAlchemy` 2.x async + `aiosqlite`,
`Alembic`, `APScheduler` (в том же event loop), `pydantic-settings`, `gspread` (Sheets),
`whisper.cpp` (голос), провайдер-агностичный LLM-слой. **Один процесс**, без n8n. Деплой — Docker Compose.

## Куда смотреть за деталями (не читать всё сразу)

| Нужно | Файл |
|---|---|
| Полное ТЗ: архитектура, модель данных, потоки, промпты | `TZ_bot_tracker.md` (по разделам §N) |
| Правила кода, структура, локальный запуск, Alembic | `plan/CONVENTIONS.md` |
| Статус этапов + **заметки между этапами** (где что лежит) | `plan/PROGRESS.md` |
| Разбивка ТЗ по этапам, что читать под задачу | `plan/README.md` + `plan/stage-N-*.md` |
| Пользовательская инструкция, команды, troubleshooting | `README.md` |
| Деплой на VPS, скрипты, бэкапы | `docs/DEPLOY.md`, `scripts/` |
| **Новый инстанс без Docker** (venv, systemd, Google Sheets) | `docs/SETUP_INSTANCE.md` |

> `plan/PROGRESS.md` → раздел «Заметки между этапами» — самая быстрая карта того,
> в каком модуле реализована каждая фича (миграции, callback-форматы, сервисы).

## Структура кода (фактическая)

```
app/
├── main.py                 # запуск бота + планировщика
├── config.py               # pydantic-settings (.env)
├── scheduler.py            # APScheduler: одна minute_tick джоба (не per-member)
├── db/{models,session,repo}.py   # доступ к БД — только через repo.py
├── bot/
│   ├── routers/            # onboarding, tasks, checkin, decompose, settings,
│   │                       #   common, facilitator, membership
│   ├── keyboards.py, states.py, fsm_sync.py, command_names.py, messages.py …
├── llm/{client.py, prompts.py, providers/}   # ask_llm + фолбэк; gemini/openai/anthropic/openrouter
└── services/              # extraction, checkin, decompose, summary, plaud,
                           #   plaud_action_plan, voice, sheets, stats, midweek,
                           #   goal_setup, auto_goal_setup, membership, tracking …
alembic/   scripts/   deploy/   tests/   data/(app.db, в .gitignore)
```

## Ключевые доменные понятия

- **Две оси приватности** (независимые): вход `input_mode` = `auto` (из транскрипта Plaud) /
  `private` (ввод боту); видимость `visibility` = `group` / `facilitator` / `private`.
- **Участник всегда первым видит свой итог недели**; сводка уходит только после подтверждения.
- **Декомпозиция затыка — только по согласию**, не навязана.
- **Ведущих может быть несколько** — источник правды `group_facilitator`
  (поле `"group".facilitator_chat_id` — устаревшая денормализация).
- **Plaud**: транскрипт в `week.transcript_text`; блок «План действий» парсится
  без LLM (`plaud_action_plan.py`), извлечение задач — с LLM (промпт 1).
- Таблица группы называется `"group"` (в кавычках, зарезервированное слово).

## Модель данных (кратко; детали — §5 ТЗ)

`group` · `member` (input_mode, visibility, checkin_weekday/time, timezone, midweek_ping) ·
`week` (transcript_text, plaud_url) · `task` (source `plaud|manual|decomposed`,
status `pending|done|in_progress|stuck|decomposed`, parent_task_id, confirmed) ·
`dialog_state` (state + context_json — **источник правды диалога, не память FSM**) ·
`summary` (member_text / facilitator_text / shared_scope) · `group_facilitator` · `membership_request`.

## Команды (актуальные имена — `app/bot/command_names.py`)

Участник: `/start`, `/settings`, `/my_goals_set`, `/my_goals_view`, `/my_goals_update`,
`/my_goals_stats`, `/my_goals_submit`, `/help`.
Ведущий (только chat_id из `group_facilitator`): `/group`, `/group_invite`, `/group_members`,
`/group_requests`, `/group_set_plaud`, `/group_paste_transcript`, `/group_paste_done`,
`/group_view_goals`, `/group_sync_goals`.

## Правила кода (всегда соблюдать; полностью — `plan/CONVENTIONS.md`)

- Везде `async/await`; никаких блокирующих вызовов в хендлерах.
- Доступ к БД — только через `app/db/repo.py`.
- Состояние диалога — в БД (`dialog_state`), FSM aiogram синхронизируется с ним (переживает рестарт).
- `callback_data` компактный, ≤ 64 байт (чек-ин: `t:{task_id}:{status}`).
- Секреты только из `.env` через `config.py`; тексты пользователю — на русском, в тоне «напарник».
- Меняешь схему → **добавляй миграцию Alembic**. Никаких SQLite-специфичных
  конструкций (должно переноситься на Postgres).
- Тесты — на нетривиальную чистую логику; LLM/Telegram/Sheets мокать.

## Запуск и миграции

```bash
# Локально (Docker, рекоменд.): в .env задать TELEGRAM_BOT_TOKEN и UID/GID (= id -u / id -g)
docker compose up --build            # миграции применяются на старте
# venv: pip install -e ".[dev]"; alembic upgrade head; python -m app.main

alembic revision --autogenerate -m "описание"   # после правки моделей
```

Деплой на VPS — `./scripts/deploy.sh` (детали и troubleshooting в `docs/DEPLOY.md`).

## Definition of Done (для любой задачи)

Код запускается без ошибок импорта · миграции применены (если менялась схема) ·
линтер/типы чистые в изменённых файлах · при завершении этапа/фичи — обновить
`plan/PROGRESS.md` (чекбокс + короткая заметка).

# Общие правила (читать на каждом этапе)

Этот файл — единый свод правил для всех этапов. Он не повторяется в файлах
этапов, поэтому читай его всегда вместе со «своим» этапом.

## Стек (из §3 ТЗ)

- Python 3.12+, `aiogram` 3.x (async, long polling).
- `SQLAlchemy` 2.x async + `aiosqlite`, миграции `Alembic`.
- `APScheduler` (AsyncIOScheduler) в том же event loop.
- LLM — провайдер-агностичный слой (§8). Голос — `whisper.cpp` (§14).
- `gspread` (service account) для витрины. Конфиг — `pydantic-settings` + `.env`.
- Без n8n: один Python-процесс.

## Структура проекта (целевая, из §13)

```
bot_tracker/
├── app/
│   ├── main.py            # запуск бота + планировщика
│   ├── config.py          # pydantic-settings
│   ├── db/{models,session,repo}.py
│   ├── bot/
│   │   ├── routers/       # onboarding, tasks, checkin, decompose, settings, common
│   │   ├── keyboards.py
│   │   └── states.py      # FSM
│   ├── llm/{client.py, providers/, prompts.py}
│   ├── services/{extraction,checkin,decompose,summary,plaud,voice,sheets}.py
│   └── scheduler.py
├── alembic/
├── data/                  # app.db (в .gitignore)
├── tests/
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
└── README.md
```

> Файлы создаются по мере этапов — не нужно делать всё сразу. Каждый этап
> явно говорит, какие модули он трогает.

## Принципы продукта, которые влияют на код (§2 ТЗ)

- Тон бота — поддерживающий **напарник**, не контролёр. Это про формулировки
  всех сообщений пользователю.
- Минимум печати: где есть выбор — инлайн-кнопки. Свободный текст/голос — только
  где он содержательно нужен.
- Приватность: вход (`auto`/`private`) и видимость (`group`/`facilitator`/`private`) —
  независимые оси. Участник **всегда первым видит свой итог**.
- Декомпозиция и любые «дробления» — только **по согласию**.

## Правила кода

- Везде `async/await`. Никаких синхронных блокирующих вызовов в хендлерах
  (LLM/HTTP/whisper — через `await`/`run_in_executor`).
- Источник правды состояния диалога — **БД** (`dialog_state`), а не память FSM.
  FSM aiogram синхронизируется с `dialog_state.state`, чтобы переживать рестарт (§7).
- Доступ к БД — только через `app/db/repo.py` (репозиторий-функции), хендлеры
  не пишут запросы напрямую.
- `callback_data` для чек-ина — формат `t:{task_id}:{status}`, держать ≤ 64 байт (§6.4).
- Все секреты — из `.env` через `config.py`. Никаких хардкодов токенов/ключей.
- Тексты сообщений пользователю — на русском, в тоне «напарник».
- Не ломай обратную совместимость моделей: меняешь схему — добавляешь миграцию Alembic.
- Смена `DATABASE_URL` на Postgres не должна требовать правок бизнес-логики
  (никаких SQLite-специфичных конструкций в запросах).

## Зависимости (добавлять по мере надобности, актуальные версии)

Базовый набор для этапа 0: `aiogram`, `sqlalchemy[asyncio]`, `aiosqlite`,
`alembic`, `apscheduler`, `pydantic-settings`. Остальное (`httpx`, `gspread`,
провайдеры LLM) добавляется на профильных этапах. Версии не выдумывать —
ставить актуальные через менеджер пакетов.

## Локальный запуск

Вариант A — Docker (рекомендуется):
```bash
cp .env.example .env   # заполнить TELEGRAM_BOT_TOKEN тестового бота
docker compose up --build
```

Вариант B — venv:
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
alembic upgrade head
python -m app.main
```

## Alembic

- Async-движок: `alembic/env.py` настроен на async-engine из `app/db/session.py`.
- Новая миграция: `alembic revision --autogenerate -m "описание"`,
  применить: `alembic upgrade head`.
- В Docker миграции прогоняются на старте контейнера (entrypoint) перед запуском бота.

## Работа с агентом (контекст)

Этапы рассчитаны на самодостаточные запуски (см. `plan/README.md`). Если в текущем
чате накопилось много истории и агент путается — **начни новый чат** на следующий
этап, приложив только `plan/stage-N-*.md` и `plan/CONVENTIONS.md`. Это нормальная
практика, а не признак проблемы.

## Тестирование

- Лёгкие unit-тесты на чистую логику (парсинг callback_data, маршрутизация
  видимости, разбор статусов). LLM/Telegram/Sheets — мокать.
- Не гнаться за покрытием: тесты там, где есть нетривиальная логика.

## Definition of Done (общее для любого этапа)

- Код запускается (`docker compose up` / `python -m app.main`) без ошибок импорта.
- Применены миграции, если менялась схема.
- Линтер/типы без явных ошибок в изменённых файлах.
- Локальная проверка из файла этапа пройдена.
- Обновлён `plan/PROGRESS.md`.

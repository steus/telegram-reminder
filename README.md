# bot-tracker

Telegram-бот для недельного peer-accountability трекинга задач бизнес-группы.
Тон бота — поддерживающий напарник, а не контролёр. Полное ТЗ — в
[`TZ_bot_tracker.md`](./TZ_bot_tracker.md), план сборки по этапам — в [`plan/`](./plan).

Текущий статус: **этап 7 — прогресс и деплой**. Полный поток: онбординг, задачи
(ручной и auto из Plaud), чек-ин, декомпозиция, голос, итоги и Sheets, `/stats`,
midweek-пинг, прод через Docker Compose.

## Стек

Python 3.12+, aiogram 3.x, SQLAlchemy 2.x (async) + aiosqlite, Alembic,
APScheduler, pydantic-settings. Один процесс: бот + планировщик в общем event loop.

## Запуск локально

### Вариант A — Docker (рекомендуется)

```bash
cp .env.example .env          # вписать TELEGRAM_BOT_TOKEN; UID/GID = id -u / id -g
docker compose up --build
```

В `.env` задай `UID` и `GID` (см. `.env.example`) — иначе контейнер не сможет писать в `./data/app.db`.
Альтернатива одной строкой: `export UID=$(id -u) GID=$(id -g)` перед `docker compose up`.

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
# Docker (после docker compose up --build):
docker compose exec bot python scripts/seed_member.py --chat-id ВАШ_CHAT_ID --name "Ваше Имя"

# или с хоста (venv):
python scripts/seed_member.py --chat-id ВАШ_CHAT_ID --name "Ваше Имя"
```

Затем отправь боту `/start` — пройди онбординг кнопками.

**Альтернатива — вступление через бота (этап 6b):** ведущий отправляет
`/group_invite` и передаёт ссылку новому участнику. Тот подаёт заявку; любой
ведущий принимает или отклоняет её кнопками. После одобрения — снова `/start`
и онбординг. Имя при заявке — латиницей (для Plaud).

Незнакомый chat_id без invite-ссылки получит подсказку обратиться к ведущему.

### Ведущие группы (facilitator)

У группы может быть **несколько ведущих**. Их Telegram chat_id хранятся в таблице
`group_facilitator` (не в `groups` — таблица называется `"group"`). Команды ведущего:
`/group_invite`, `/group_members`, `/group_requests`,
`/group_set_plaud`, `/group_paste_transcript`.

Поле `"group".facilitator_chat_id` — устаревшая денормализация (первый ведущий в
списке); для проверки прав бот смотрит только `group_facilitator`.

**Первый ведущий** — при создании группы через seed:

```bash
docker compose exec bot python scripts/seed_member.py \
  --chat-id CHAT_ID_УЧАСТНИКА \
  --name "Иван Петров" \
  --facilitator-chat-id CHAT_ID_ВЕДУЩЕГО
```

Если `--facilitator-chat-id` не указан, ведущим становится chat_id участника из `--chat-id`.

**Несколько ведущих сразу** (при создании группы или при добавлении участника в
существующую — новые id допишутся в `group_facilitator`):

```bash
docker compose exec bot python scripts/seed_member.py \
  --chat-id CHAT_ID_УЧАСТНИКА \
  --name "Иван" \
  --facilitator-chat-id 111111111,222222222

# или несколько флагов:
docker compose exec bot python scripts/seed_member.py \
  --chat-id CHAT_ID_УЧАСТНИКА \
  --name "Иван" \
  --facilitator-chat-id 111111111 \
  --facilitator-chat-id 222222222
```

**Добавить второго ведущего в уже существующую группу** — через SQL (бот
остановлен, DB Browser закрыт — иначе `database is locked`):

```bash
docker compose stop bot

sqlite3 data/app.db \
  "INSERT INTO group_facilitator (group_id, telegram_chat_id) VALUES (1, 'CHAT_ID_ВТОРОГО_ВЕДУЩЕГО');"

sqlite3 data/app.db \
  "SELECT g.id, g.name, gf.telegram_chat_id
   FROM group_facilitator gf
   JOIN \"group\" g ON g.id = gf.group_id;"

docker compose up -d
```

`group_id = 1` замени на id своей группы (смотри в `"group"`).

**Проверка:** от аккаунта ведущего в личке боту — `/paste_transcript`. Если chat_id
не в `group_facilitator`, бот покажет твой chat_id в сообщении об ошибке.

## Команды Telegram

Справка в боте: `/help`. Незарегистрированный chat_id получит отказ — сначала seed + `/start`.

### Участник (все)

| Команда | Описание |
|---------|----------|
| `/start` | Онбординг: способ ввода задач, видимость, день/время чек-ина, midweek-пинг |
| `/settings` | Изменить настройки (кнопки) |
| `/my_goals_set` | Задать задачи на неделю (режим **private**) |
| `/my_goals_view` | Задачи и статусы на эту неделю |
| `/my_goals_submit` | Обновить задачи в таблице (вкладка «Прогресс») |
| `/my_goals_update` | Обновить статус моих задач (вручную; в проде — по расписанию) |
| `/stats` | Серия недель, % выполнения, частые затыки |

**Режим ввода задач** (`/settings` → «Способ ввода»):

- **Вручную** (`private`) — `/my_goals_set`, список строк → экран подтверждения (кнопки «Всё верно» / «Исправить»).
- **Из транскрипта** (`auto`) — задачи приходят после встречи от ведущего; нужно подтвердить список.

**Чек-ин:** бот присылает задачи с кнопками ✅ Сделал / 🔄 В работе / ⛔ Затык. Можно ответить текстом или голосом *(LLM-трекинг — этап 5)*.

**Имя в базе** (`member.full_name` из seed) должно совпадать с именем в транскрипте Plaud: «Stepan» ↔ «@Степан», «Speaker 1» ↔ участник с `--name "Speaker 1"`.

### Ведущий группы

Доступно только chat_id из таблицы `group_facilitator` (см. раздел ниже).

| Команда | Описание |
|---------|----------|
| `/set_plaud_url URL` | Сохранить ссылку на транскрипт Plaud для текущей недели |
| `/paste_transcript` | Начать ручную вставку транскрипта / блока «План действий» |
| `/paste_done` | Завершить многочастную вставку (см. сценарии ниже) |

**Вставка транскрипта — три сценария:**

1. **Только своя секция** — одним сообщением, без `/paste_transcript`:
   ```
   @Степан (Speaker 3)
   Довести до конца вопросы с бухгалтерией - [TBD]
   ...
   ```
   Бот сразу разберёт @-секцию и разошлёт задачи участникам в режиме `auto`.

2. **Весь «План действий» одним сообщением** — `/paste_transcript`, затем текст с **двумя и более** @-заголовками → сразу обработка.

3. **По частям** — `/paste_transcript` → `@Speaker 1 …` → `@Степан …` → … → **`/paste_done`**.  
   После каждой части бот ответит «Принял (N символов)…».

**Повторная вставка** после рассылки: бот спросит «Разослать заново» или «Только сохранить».

**Отчёт ведущему** после обработки: кому отправлен экран подтверждения, у кого нет задач в транскрипте, кто не в режиме `auto`.

### Типичный сценарий недели

1. Встреча → ведущий `/paste_transcript` + блок Plaud «План действий».
2. Участники `auto` получают список задач → подтверждают.
3. В день чек-ина — кнопки статусов по каждой задаче.

### Устранение проблем

| Симптом | Что проверить |
|---------|----------------|
| «Эта команда доступна только ведущему» | chat_id в `group_facilitator`; бот покажет твой id |
| «0 участник(ам) auto» | `/settings` → «Из транскрипта встречи» |
| Чужие задачи у участника | Имя в seed ≠ секция @ в Plaud; для «План действий» LLM не нужен — парсер @-секций |
| Нет ответа / ошибка БД | Закрыть DB Browser; в `.env` указать `UID`/`GID` = `id -u` / `id -g`; `docker compose up --build -d` |
| `database is locked` | Остановить бота, закрыть все программы с `data/app.db`, запустить снова |

---

## Auto-режим и транскрипт Plaud (этап 4)

1. Участник: `/settings` → «Способ ввода задач» → «Из транскрипта встречи».
2. `member.full_name` должно **совпадать с именем в транскрипте** (допускается
   частичное совпадение: «Stepan» / «Stepan Teus», «@Степан»). Метки Plaud «Speaker 1» —
   отдельные секции, не путать с реальными именами.
3. Ведущий вставляет транскрипт (см. **Команды Telegram** выше).
4. Повторная вставка после рассылки — бот спросит: разослать заново или только
   сохранить текст.

## Задачи на неделю (этап 2)

После онбординга (режим `private`):

```bash
# в Telegram:
/my_goals_set      # ввести задачи списком → подтвердить кнопкой
/my_goals_view     # посмотреть текущий список
/my_goals_update   # обновить статусы вручную (для разработки)
```

По расписанию статусы запрашивает бот сам — день/время из онбординга (`/settings`).

## Полезное

```bash
# Миграции (Docker — автоматически на старте; venv — вручную):
docker compose exec bot alembic upgrade head
# или: .venv/bin/alembic upgrade head

# Новая миграция после правки моделей
alembic revision --autogenerate -m "описание"
alembic upgrade head

# Ведущие группы
sqlite3 data/app.db "SELECT * FROM group_facilitator;"

# Проверить таблицы в SQLite
python -c "import sqlite3; print(sqlite3.connect('data/app.db').execute(\
  'select name from sqlite_master where type=\"table\"').fetchall())"
```

## Деплой на VPS (Docker, основной путь)

**Краткая инструкция:** [`docs/DEPLOY.md`](./docs/DEPLOY.md).

```bash
git clone <repo> /opt/bot-tracker && cd /opt/bot-tracker
./scripts/deploy.sh --init          # .env + UID/GID
nano .env                           # токен, LLM, Sheets…
./scripts/deploy.sh                 # pull + build + up -d
./scripts/deploy.sh --logs          # проверка
```

Обновление после push: `./scripts/deploy.sh`.  
БД с локали: `./scripts/deploy.sh --db /path/to/app.db`.  
Права на `data/`: `./scripts/deploy.sh --fix-perms`.

**Whisper в проде:** либо смонтировать бинарь и модель в `docker-compose.yml`
(см. комментарий в файле), либо `WHISPER_MODE=api` и `OPENAI_API_KEY` в `.env`.

### Бэкапы БД

Скрипт `scripts/backup_db.sh` копирует `data/app.db` в `./backups/` (ротация 14 дней).

```bash
./scripts/backup_db.sh
```

Пример cron на хосте (ежедневно в 03:00):

```cron
0 3 * * * cd /opt/bot-tracker && ./scripts/backup_db.sh >> /var/log/bot-tracker-backup.log 2>&1
```

При Docker том `./data` остаётся на хосте — бэкап запускается с хоста по тому же пути.

### Альтернатива: systemd без Docker

См. `deploy/bot-tracker.service`: venv в `/opt/bot-tracker`, `EnvironmentFile=.env`,
автозапуск и рестарт, логи в `journalctl -u bot-tracker -f`. Перед первым запуском:
`alembic upgrade head`, права на `data/` для пользователя сервиса.

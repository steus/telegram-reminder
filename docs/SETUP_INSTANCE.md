# Запуск нового инстанса бота (без Docker)

Инструкция для развёртывания **отдельного** Telegram-бота: свой токен, своя БД,
своя Google Таблица. Подходит для клиентских копий на том же VPS, где уже работает
другой инстанс (Docker или direct).

> Docker-деплой основного бота — см. [`DEPLOY.md`](DEPLOY.md).  
> Готовый пошаговый пример — [Приложение: Marina School](#приложение-рецепт-marina-school-рабочий-пример).

---

## Что нужно заранее

| Что | Где взять |
|-----|-----------|
| Токен Telegram-бота | [@BotFather](https://t.me/BotFather) — **отдельный бот** на каждый инстанс |
| Репозиторий на VPS | `git clone` в **свою папку** (не копировать папку руками) |
| Ветка / тег | `main`, `stable` или тег `v1.x-stable` — см. раздел [Версия кода](#версия-кода) |
| LLM API-ключ | Gemini / OpenAI / OpenRouter — по выбору |
| OpenAI API-ключ | Если `WHISPER_MODE=api` (рекомендуется на слабом VPS) |
| Google Service Account | См. [Google Sheets](#google-sheets-пошагово) |
| Google Таблица | Отдельная на каждый инстанс |
| Telegram chat_id ведущего | Через **`/group`** в боте или [@userinfobot](https://t.me/userinfobot) — см. [§5.1](#51-как-узнать-свой-chat_id-обязательно-перед-seed) |

---

## Быстрый чеклист

```text
1. git clone → cd в папку инстанса
2. git checkout <ветка или тег>
3. bash scripts/setup_direct.sh
4. nano .env          — токен, LLM, Whisper, путь к Google JSON, INSTANCE_CONFIG
5. Запуск бота        — .venv/bin/python -m app.main (или systemd)
6. /group в Telegram  — узнать свой chat_id (ВАЖНО, см. §5)
7. seed_member.py     — первый участник / ведущий с правильным chat_id
8. sheet_id в БД      — привязать Google Таблицу
9. /start в Telegram  — онбординг
10. systemd           — постоянный запуск (если ещё не настроен)
```

---

## 1. Клонирование и версия кода

```bash
git clone <repo-url> /opt/bot-school
cd /opt/bot-school
```

### Версия кода

- **Стабильная линия для клиента:** `git checkout stable` или `git checkout v1.0-stable`
- **Актуальная разработка:** остаться на `main`

Код у всех инстансов **один и тот же** (разные версии из git). Отличия между
ботами — в `.env`, `config/instances/*.json`, `./data/` и `sheet_id` группы в БД.

---

## 2. Подготовка окружения

```bash
bash scripts/setup_direct.sh
```

Скрипт (идемпотентный, можно повторять):

- ставит `python3.12`, `python3.12-venv`, `ffmpeg`, `git` (через apt, если нужно);
- создаёт `.venv` и `pip install -e .` (editable — апдейт кода без пересборки);
- копирует `.env.example` → `.env`, если файла нет;
- применяет миграции: `alembic upgrade head`.

Флаги:

| Флаг | Когда |
|------|-------|
| `--no-apt` | Системные пакеты уже стоят / нет sudo |
| `--no-migrate` | Миграции позже вручную |
| `--with-dev` | pytest, ruff (для разработки) |

Проверка запуска:

```bash
.venv/bin/python -m app.main
# Ctrl+C после «Starting polling»
```

### Если `setup_direct.sh` падает на venv

Типичная ошибка на Ubuntu/Debian с Python 3.14:

```text
ensurepip is not available … apt install python3.14-venv
```

Решение:

```bash
sudo apt install python3.14-venv    # или python3.12 python3.12-venv
rm -rf .venv
bash scripts/setup_direct.sh
```

Скрипт `setup_direct.sh` в актуальной версии репозитория ставит нужный пакет
`pythonX.Y-venv` автоматически; если на VPS старая копия скрипта — выполните
команды выше вручную или сделайте `git pull`.

---

## 3. Настройка `.env`

Откройте `.env` и заполните минимум:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC...          # свой токен от BotFather

DATABASE_URL=sqlite+aiosqlite:///./data/app.db   # НЕ МЕНЯТЬ (см. ниже)
DEFAULT_TIMEZONE=Europe/Moscow            # часовой пояс группы

LLM_PROVIDER=openrouter                   # gemini | openai | anthropic | openrouter
LLM_MODEL=google/gemini-2.5-flash
LLM_API_KEY=sk-...

WHISPER_MODE=api
OPENAI_API_KEY=sk-...                     # для Whisper API

GOOGLE_SERVICE_ACCOUNT_JSON=/opt/bot-school/credentials/google-sa.json

# Опционально: шаги онбординга и фичи инстанса (см. §3.1)
INSTANCE_CONFIG=config/instances/default.json
```

### 3.1. Конфиг инстанса (`INSTANCE_CONFIG`)

Для каждого проекта можно задать отдельный JSON с особенностями логики —
какие шаги онбординга включать, какие фичи использовать.

Файлы лежат в `config/instances/`:

| Файл | Назначение |
|------|------------|
| `default.json` | Базовый онбординг без email/телефона |
| `marina.json` | Сбор email и телефона на `/start` |

В `.env` укажите путь (относительно папки проекта или абсолютный):

```bash
INSTANCE_CONFIG=config/instances/marina.json
```

Если переменная не задана — используется `config/instances/default.json`.

Пример `config/instances/marina.json`:

```json
{
  "id": "marina",
  "onboarding": {
    "collect_email": true,
    "collect_phone": true
  },
  "features": {
    "jtbd_profile": false
  }
}
```

При включённых `collect_email` / `collect_phone` бот спрашивает контакты
после шага «видимость итога недели», до выбора дня чек-ина. Уже онбордившиеся
участники могут указать или изменить их в `/settings`. Данные сохраняются
в таблице `member` и видны ведущему в `/group_members`.

Флаг `jtbd_profile` зарезервирован под расширенную JTBD-анкету (ветка `main`);
на `stable` пока не используется.

Новый инстанс: скопируйте `default.json` → `my-project.json`, включите нужные
флаги и пропишите путь в `.env`.

### DATABASE_URL — менять не нужно

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
```

Путь `./data/app.db` — **относительный к папке проекта**. У каждого инстанса
свой клон → своя `./data/app.db`. Изоляция данных автоматическая.

Менять только при переезде на Postgres.

### UID / GID — для direct-запуска не нужны

Строки `UID=` / `GID=` в `.env` используются **только Docker**-инстансом.
При запуске через systemd/vvenv их можно не заполнять.

Важно: каталог `./data/` должен принадлежать пользователю, от которого
работает systemd-юнит (`chown user:user data/`).

### WHISPER_MODE=api (рекомендуется)

Не требует установки whisper.cpp. Достаточно `OPENAI_API_KEY`.
Для `WHISPER_MODE=local` — см. `scripts/setup_whisper_local.sh`.

---

## 4. Google Sheets — пошагово

Бот пишет в Google Таблицу **финальные сводки** и **прогресс задач** (вкладка
«Прогресс»). Доступ — через **Service Account** (не OAuth, не «User data»).

### 4.1. Google Cloud Console

1. Откройте [console.cloud.google.com](https://console.cloud.google.com).
2. Создайте проект (или выберите существующий).
3. **APIs & Services → Library** → включите **Google Sheets API**.

### 4.2. Service Account

1. **APIs & Services → Credentials → Create credentials → Service account**.
2. Если мастер спрашивает тип данных — выберите **Application data**
   (не «User data» — тот вариант для OAuth от имени пользователя).
3. Создайте service account, откройте его → **Keys → Add key → Create new key → JSON**.
4. Скачается файл, например `my-project-abc123.json`.

> Один service account можно использовать для **нескольких ботов** — у каждого
> своя таблица и свой `sheet_id` в БД.

### 4.3. JSON на сервере

```bash
mkdir -p /opt/bot-school/credentials
chmod 700 /opt/bot-school/credentials
scp my-project-abc123.json user@vps:/opt/bot-school/credentials/google-sa.json
chmod 600 /opt/bot-school/credentials/google-sa.json
```

В `.env`:

```bash
GOOGLE_SERVICE_ACCOUNT_JSON=/opt/bot-school/credentials/google-sa.json
```

Альтернатива — inline JSON в одну строку (начинается с `{`), но **путь к файлу
удобнее** и безопаснее.

В JSON найдите поле `"client_email"` — понадобится на следующем шаге.

### 4.4. Google Таблица

1. Создайте **новую** Google Таблицу (отдельную от других ботов).
2. **Share (Поделиться)** → добавьте `client_email` из JSON → роль **Editor**.
3. Скопируйте **sheet_id** из URL:

```text
https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                      sheet_id
```

### 4.5. Привязка таблицы к группе в БД

`sheet_id` хранится в таблице `"group"` (SQLite), **не в `.env`**.

После создания группы (seed или онбординг):

```bash
cd /opt/bot-school
sqlite3 data/app.db "SELECT id, name, sheet_id FROM \"group\";"
sqlite3 data/app.db "UPDATE \"group\" SET sheet_id='1AbCdEfGhIjKlMnOpQrStUvWxYz' WHERE id=1;"
```

Можно указать `sheet_id` сразу при seed (если группа ещё не создана — после
первого seed, когда появится запись в `"group"`).

### 4.6. Проверка Sheets

1. Запустите бота.
2. Ведущий в Telegram: `/group_sync_goals`.
3. В таблице должна появиться вкладка **«Прогресс»** с заголовками
   (бот создаст её сам, если листа нет).
4. На первом листе (`Sheet1`) при итогах недели появятся строки сводок
   (колонки: Неделя, Участник, Сводка участника, Резюме для ведущего).

### Что пишется в таблицу

| Вкладка | Когда | Кто видит |
|---------|-------|-----------|
| `Sheet1` | Финальная сводка недели (после подтверждения участником) | Только участники с `visibility=group` |
| `Прогресс` | `/group_sync_goals` или синхронизация задач | То же |

Участники с `visibility=private` или `facilitator` **не попадают** в групповую таблицу.

### Частые ошибки Sheets

| Симптом | Причина | Решение |
|---------|---------|---------|
| «Не настроен GOOGLE_SERVICE_ACCOUNT_JSON» | Пустой `.env` или неверный путь | Проверить путь, `chmod 600` на JSON |
| «У группы не настроена таблица (sheet_id)» | `sheet_id` NULL в БД | UPDATE в `"group"` |
| `403 Permission denied` | Таблица не расшарена на service account | Share → `client_email` → Editor |
| `404 Spreadsheet not found` | Неверный `sheet_id` | Проверить URL таблицы |
| Запись не появляется | У участника `visibility` не `group` | `/settings` → «Группе» |

---

## 5. Первый ведущий и участник (seed)

### 5.1. Как узнать свой chat_id (обязательно перед seed)

Telegram **chat_id** — это число вида `379481763`. Это **не** номер телефона
и не username.

**Рекомендуемый способ** (самый надёжный для этого бота):

1. Запустите бота (хотя бы на минуту): `.venv/bin/python -m app.main`
2. Напишите боту **`/group`**
3. Бот ответит:

   ```text
   Эта команда доступна только ведущему группы.
   Твой chat_id в этом чате: 379481763
   ```

4. Это число и подставляйте в seed.

Альтернатива: [@userinfobot](https://t.me/userinfobot) — поле **Id**.

> **Частая ошибка:** подставить номер телефона или другое число — seed создаст
> запись, но `/start` будет отвечать «нет активной группы», потому что бот ищет
> участника по **реальному** chat_id из Telegram.

### 5.2. Seed — группа + ведущий + участник

```bash
cd /opt/bot-school

.venv/bin/python scripts/seed_member.py \
  --chat-id 379481763 \
  --name "Stepan Teus" \
  --group "Marina School" \
  --facilitator-chat-id 379481763
```

`--facilitator-chat-id` можно опустить — по умолчанию равен `--chat-id`.

### 5.3. Привязать Google Таблицу (если ещё не сделали)

```bash
sqlite3 data/app.db "UPDATE \"group\" SET sheet_id='ID_ИЗ_URL_ТАБЛИЦЫ' WHERE id=1;"
```

### 5.4. Проверка записей в БД

```bash
sqlite3 data/app.db "SELECT id, full_name, telegram_chat_id, is_active FROM member;"
sqlite3 data/app.db "SELECT * FROM group_facilitator;"
sqlite3 data/app.db "SELECT id, name, sheet_id FROM \"group\";"
```

Ожидаемо:

- в `member` и `group_facilitator` один и тот же `telegram_chat_id`;
- `is_active = 1`;
- `sheet_id` заполнен (если Sheets нужен).

### 5.5. Онбординг в Telegram

`/start` → пройти шаги (режим ввода, видимость, время чек-ина).

После онбординга ведущий: `/group` → меню ведущего, `/group_invite` → ссылка
для других участников.

### 5.6. Исправить неверный chat_id

Если seed уже выполнен с неправильным id (бот пишет «нет активной группы»,
а в БД участник есть):

1. Узнайте реальный id: **`/group`** в боте.
2. Обновите все три места:

```bash
cd /opt/bot-school
REAL=379481763   # ваш chat_id из ответа бота

sqlite3 data/app.db "UPDATE member SET telegram_chat_id='$REAL' WHERE id=1;"
sqlite3 data/app.db "UPDATE group_facilitator SET telegram_chat_id='$REAL' WHERE group_id=1;"
sqlite3 data/app.db "UPDATE \"group\" SET facilitator_chat_id='$REAL' WHERE id=1;"
```

3. Снова `/start` в Telegram.

### 5.7. Seed говорит «участник уже существует»

Запись с таким `chat_id` уже есть — seed не перезаписывает. Варианты:

- если chat_id **верный** — просто `/start`;
- если chat_id **неверный** — см. [§5.6](#56-исправить-неверный-chat_id);
- если нужно начать с нуля (один участник, тестовая БД):

```bash
sqlite3 data/app.db "DELETE FROM dialog_state; DELETE FROM member; DELETE FROM group_facilitator; DELETE FROM \"group\";"
# затем seed заново с правильным chat_id
```

## 6. Постоянный запуск (systemd)

Скопируйте шаблон и **задайте уникальное имя** юнита на каждый инстанс:

```bash
sudo cp deploy/bot-tracker.service /etc/systemd/system/bot-school.service
sudo nano /etc/systemd/system/bot-school.service
```

Поправьте:

```ini
[Service]
User=YOUR_USER                    # пользователь VPS (владелец папки)
Group=YOUR_USER
WorkingDirectory=/opt/bot-school
EnvironmentFile=/opt/bot-school/.env
ExecStartPre=/opt/bot-school/.venv/bin/alembic upgrade head
ExecStart=/opt/bot-school/.venv/bin/python -m app.main
ReadWritePaths=/opt/bot-school/data
```

`ExecStartPre` применяет миграции при каждом старте (как Docker entrypoint).

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-school
journalctl -u bot-school -f          # логи
```

---

## 7. Обновление кода

Обычный апдейт (изменился только код, без новых зависимостей и миграций):

```bash
cd /opt/bot-school
git pull
sudo systemctl restart bot-school     # ~2–5 сек
```

Если изменились зависимости (`pyproject.toml`):

```bash
git pull
.venv/bin/pip install -e .
sudo systemctl restart bot-school
```

Если появились миграции Alembic (без `ExecStartPre` в юните):

```bash
git pull
.venv/bin/alembic upgrade head
sudo systemctl restart bot-school
```

Обновление стабильной линии клиента:

```bash
git fetch --tags
git checkout v1.1-stable            # или git merge main на ветке stable
sudo systemctl restart bot-school
```

---

## 8. Несколько ботов на одном VPS

| | Инстанс A (Docker) | Инстанс B (direct) |
|--|-------------------|-------------------|
| Папка | `/opt/bot-tracker` | `/opt/bot-school` |
| Запуск | `docker compose` | systemd `bot-school` |
| БД | `./data/app.db` | `./data/app.db` (своя) |
| Токен | свой | свой |
| Таблица | своя | своя |
| `.env` | свой | свой |
| Порты | не нужны (long polling) | не нужны |

Конфликтов нет: long polling, разные токены, разные папки.

---

## 9. Бэкапы

```bash
cd /opt/bot-school
./scripts/backup_db.sh
```

Cron (отдельная строка на каждый инстанс):

```cron
0 3 * * * cd /opt/bot-school && ./scripts/backup_db.sh >> /var/log/bot-school-backup.log 2>&1
```

> `backup_db.sh` рассчитан на Docker-окружение. Для direct-запуска достаточно
> копировать `data/app.db` в `./backups/` вручную или адаптировать cron:

```cron
0 3 * * * cp /opt/bot-school/data/app.db /opt/bot-school/backups/app_$(date +\%Y\%m\%d).db
```

---

## 10. Частые проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| Бот не отвечает | Не запущен / неверный токен | `journalctl -u bot-school -f`; проверить `TELEGRAM_BOT_TOKEN` |
| «Нет активной группы», в БД участник **есть** | Неверный `telegram_chat_id` в seed | `/group` → реальный id → [§5.6](#56-исправить-неверный-chat_id) |
| «Нет активной группы», в БД **пусто** | Seed не выполнялся | [§5.2](#52-seed--группа--ведущий--участник) |
| Seed: «участник уже существует» | Дубликат chat_id | [§5.7](#57-seed-говорит-участник-уже-существует) |
| `/start` не видит seed, БД «правильная» | Бот читает **другой** `app.db` | Проверить `WorkingDirectory` systemd; `find /opt -name app.db` |
| `ensurepip is not available` | Нет `python3.X-venv` | [§2](#если-setup_directsh-падает-на-venv) |
| `database is locked` | Бот + DB Browser одновременно | Остановить бота, закрыть sqlite3/DB Browser |
| Нет записи в Sheets | Credentials / share / sheet_id | [§4.6](#46-проверка-sheets), [таблица ошибок Sheets](#частые-ошибки-sheets) |
| После `git pull` старый код | Не та ветка / зависимости | `git branch`; `pip install -e .` |
| Permission denied на `data/` | Права каталога | `chown -R user:user data/` |

### Диагностика «бот не видит участника»

```bash
cd /opt/bot-school

# что в БД
sqlite3 data/app.db "SELECT id, telegram_chat_id FROM member;"

# какой app.db на диске
ls -la data/app.db

# откуда запущен процесс (должен быть /opt/bot-school)
ps aux | grep "[a]pp.main"
grep WorkingDirectory /etc/systemd/system/bot-school.service
```

Сравните `telegram_chat_id` в БД с числом из **`/group`** в Telegram.

---

## Приложение: рецепт «Marina School» (рабочий пример)

Реальный кейс: второй бот для клиентской группы на том же VPS, где основной
бот уже работает через Docker. Direct-запуск, стабильная ветка, `WHISPER_MODE=api`.

### Исходные условия

| Параметр | Значение |
|----------|----------|
| Папка на VPS | `/opt/bot-school` |
| Основной бот | `/opt/bot-tracker` (Docker, не трогаем) |
| Telegram-бот | `@MarinaP2026` (отдельный токен от BotFather) |
| Группа в БД | `Marina School` |
| Whisper | `WHISPER_MODE=api` |
| Google | отдельная таблица + service account JSON |

### Шаг 1. Клон и окружение

```bash
git clone <repo-url> /opt/bot-school
cd /opt/bot-school
git checkout stable                    # или нужный тег

bash scripts/setup_direct.sh
# если упало на venv:
#   sudo apt install python3.14-venv && rm -rf .venv && bash scripts/setup_direct.sh
```

### Шаг 2. `.env`

```bash
nano .env
```

Минимум:

```bash
TELEGRAM_BOT_TOKEN=...                 # токен @MarinaP2026

DATABASE_URL=sqlite+aiosqlite:///./data/app.db
DEFAULT_TIMEZONE=Europe/Moscow

LLM_PROVIDER=openrouter
LLM_MODEL=google/gemini-2.5-flash
LLM_API_KEY=...

WHISPER_MODE=api
OPENAI_API_KEY=sk-...

GOOGLE_SERVICE_ACCOUNT_JSON=/opt/bot-school/credentials/google-sa.json

INSTANCE_CONFIG=config/instances/marina.json
```

`UID`/`GID` — не заполняем (direct-запуск).

На онбординге бот запросит email и телефон (см. [§3.1](#31-конфиг-инстанса-instance_config)).
Контакты участников — в `/group_members` у ведущего.

### Шаг 3. Google Sheets

```bash
mkdir -p /opt/bot-school/credentials
chmod 700 /opt/bot-school/credentials
# scp JSON service account → credentials/google-sa.json
chmod 600 /opt/bot-school/credentials/google-sa.json
```

1. Google Cloud → Sheets API → Service Account → JSON-ключ.
2. Тип данных в мастере: **Application data** (не User data).
3. Новая Google Таблица → Share → `client_email` из JSON → **Editor**.
4. `sheet_id` из URL таблицы — сохранить на шаг 6.

### Шаг 4. Запуск и chat_id

```bash
cd /opt/bot-school
.venv/bin/python -m app.main
```

В Telegram (бот @MarinaP2026):

```text
/group
```

Ответ бота:

```text
Твой chat_id в этом чате: 379481763
```

→ это число идёт в seed. **Не** номер телефона.

### Шаг 5. Seed ведущего

```bash
cd /opt/bot-school

.venv/bin/python scripts/seed_member.py \
  --chat-id 379481763 \
  --name "Stepan Teus" \
  --group "Marina School" \
  --facilitator-chat-id 379481763
```

Проверка:

```bash
sqlite3 data/app.db "SELECT id, full_name, telegram_chat_id FROM member;"
sqlite3 data/app.db "SELECT * FROM group_facilitator;"
```

### Шаг 6. Привязка таблицы

```bash
sqlite3 data/app.db \
  "UPDATE \"group\" SET sheet_id='1EEoc5B91ATq-jJjAwAK7oqyztXzPe9bgvC7ExYf6PhA' WHERE id=1;"
```

### Шаг 7. Онбординг и проверка

В Telegram:

1. `/start` → пройти онбординг (режим ввода, видимость, время чек-ина).
2. `/group` → меню ведущего (должно открыться, не «нет доступа»).
3. `/group_sync_goals` → вкладка «Прогресс» в Google Таблице.

### Шаг 8. systemd (постоянный запуск)

```bash
sudo cp deploy/bot-tracker.service /etc/systemd/system/bot-school.service
sudo nano /etc/systemd/system/bot-school.service
```

```ini
WorkingDirectory=/opt/bot-school
EnvironmentFile=/opt/bot-school/.env
ExecStartPre=/opt/bot-school/.venv/bin/alembic upgrade head
ExecStart=/opt/bot-school/.venv/bin/python -m app.main
ReadWritePaths=/opt/bot-school/data
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-school
journalctl -u bot-school -f
```

### Что пошло не так (и как чинили)

**Симптом:** seed выполнен, в БД участник есть, но `/start` → «нет активной группы».

**Причина:** в seed попал неверный chat_id (`8974764240` — не Telegram ID).

**Фикс:**

```bash
REAL=379481763   # из ответа /group

sqlite3 data/app.db "UPDATE member SET telegram_chat_id='$REAL' WHERE id=1;"
sqlite3 data/app.db "UPDATE group_facilitator SET telegram_chat_id='$REAL' WHERE group_id=1;"
sqlite3 data/app.db "UPDATE \"group\" SET facilitator_chat_id='$REAL' WHERE id=1;"
```

→ `/start` заработал.

**Вывод:** всегда брать chat_id из **`/group`**, затем seed.

### Обновление кода потом

```bash
cd /opt/bot-school
git pull
sudo systemctl restart bot-school
```

---

## Ссылки

- Docker-деплой: [`DEPLOY.md`](DEPLOY.md)
- Команды бота: [`README.md`](../README.md)
- systemd-шаблон: [`deploy/bot-tracker.service`](../deploy/bot-tracker.service)
- Скрипт установки: [`scripts/setup_direct.sh`](../scripts/setup_direct.sh)

# Деплой на VPS (кратко)

Скрипты в [`scripts/`](../scripts/). БД на хосте: `./data/app.db` (том Docker, в git не попадает).

## Какой скрипт когда

| Скрипт | git pull | build | `data/app.db` |
|--------|----------|-------|----------------|
| [`deploy.sh`](../scripts/deploy.sh) | да | да | **не меняет** |
| [`rebuild.sh`](../scripts/rebuild.sh) | нет | да | **не меняет** |
| [`restart.sh`](../scripts/restart.sh) | нет | нет | **не меняет** |
| [`restore_db.sh`](../scripts/restore_db.sh) | нет | нет | **заменяет** файлом-дампом |
| [`backup_db.sh`](../scripts/backup_db.sh) | — | — | копия в `./backups/` |

После изменения только `.env` или если бот «завис» — достаточно `restart.sh`.  
После `git push` с новым кодом — `deploy.sh` (или `rebuild.sh`, если pull уже сделали вручную).  
Залить дамп с локали — только `restore_db.sh`, **не** смешивать с обычным deploy.

> Раньше было `deploy.sh --db` — убрано, чтобы не путать с обновлением кода.  
> `deploy.sh` больше не удаляет `app.db-wal` / `app.db-shm` при работающем боте.

## Первый раз на сервере

```bash
git clone <repo-url> /opt/bot-tracker
cd /opt/bot-tracker

./scripts/deploy.sh --init    # .env + UID/GID под текущего пользователя
nano .env                     # TELEGRAM_BOT_TOKEN, LLM, Sheets, при слабом VPS: WHISPER_MODE=api

./scripts/deploy.sh           # build + up -d
./scripts/deploy.sh --logs    # убедиться: Starting polling
```

Добавить себя в бота (если БД пустая):

```bash
docker compose exec bot python scripts/seed_member.py \
  --chat-id ВАШ_CHAT_ID --name "Stepan Teus" \
  --facilitator-chat-id ВАШ_CHAT_ID
```

В Telegram: `/start`.

## Обновление после `git push`

На VPS:

```bash
cd /opt/bot-tracker
./scripts/deploy.sh
```

Пересборка образа без `git pull` (код уже на диске, сменился `Dockerfile` / зависимости):

```bash
./scripts/rebuild.sh
# жёсткая пересборка без кэша Docker:
./scripts/rebuild.sh --no-cache
```

Только перезапуск контейнера:

```bash
./scripts/restart.sh
```

Проверка контейнера и даты БД на диске:

```bash
./scripts/deploy.sh --status
```

## Перенос БД с локали

`git pull` и `./scripts/deploy.sh` **не заменяют** `data/app.db`.

На **локали** (бот остановлен):

```bash
./scripts/backup_db.sh
scp backups/app_*.db user@vps:/opt/bot-tracker/
```

На **VPS**:

```bash
cd /opt/bot-tracker
./scripts/restore_db.sh /opt/bot-tracker/app_20260601.db
```

Опции: `--no-backup` (не копировать текущую БД в `backups/`), `--no-start` (только заменить файл).

Скрипт остановит бота, по умолчанию сделает бэкап текущей БД, скопирует дамп, уберёт `-wal`/`-shm`, выставит права и поднимет контейнер.

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| Код на сервере старый после deploy | Нужен **build**, не только `restart.sh` — `./scripts/rebuild.sh` или `./scripts/deploy.sh` |
| `/app/data is not writable` | `./scripts/deploy.sh --fix-perms` или выровнять `UID`/`GID` в `.env` с `id -u` / `id -g` |
| «Нет активной группы» | `seed_member.py` или invite `/group_invite` |
| `database is locked` | `docker compose stop bot`, закрыть DB Browser, `./scripts/deploy.sh` |
| БД «откатилась» после deploy | Обычный deploy БД не трогает; проверь, не вызывался ли `restore_db.sh` или старый `deploy.sh --db` |

## Бэкапы

```bash
./scripts/backup_db.sh
```

Cron (ежедневно 03:00):

```cron
0 3 * * * cd /opt/bot-tracker && ./scripts/backup_db.sh >> /var/log/bot-tracker-backup.log 2>&1
```

## Без Docker

См. [`deploy/bot-tracker.service`](../deploy/bot-tracker.service).

# Деплой на VPS (кратко)

Один скрипт: [`scripts/deploy.sh`](../scripts/deploy.sh).

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

Только перезапуск (смена `.env`, бот «завис») — без pull и без build:

```bash
./scripts/restart.sh
```

## Перенос БД с локали

На **локали** (бот остановлен):

```bash
./scripts/backup_db.sh
scp backups/app_*.db user@vps:/opt/bot-tracker/
```

На **VPS**:

```bash
cd /opt/bot-tracker
./scripts/deploy.sh --db /opt/bot-tracker/app_20260601.db
```

Скрипт сам остановит бота, скопирует файл, уберёт `-wal`/`-shm`, выставит права и поднимет контейнер.

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| `/app/data is not writable` | `./scripts/deploy.sh --fix-perms` или выровнять `UID`/`GID` в `.env` с `id -u` / `id -g` |
| «Нет активной группы» | `seed_member.py` или invite `/group_invite` |
| `database is locked` | `docker compose stop bot`, закрыть DB Browser, `./scripts/deploy.sh` |

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

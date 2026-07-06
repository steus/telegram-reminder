# Этап 6b — Вступление в группу через Telegram

> Сначала `plan/CONVENTIONS.md`, затем этот файл.

## Цель

Добавить поток вступления в группу без ручного seed: новый пользователь переходит
по invite-ссылке, подаёт заявку; любой ведущий группы одобряет или отклоняет.
Ведущие управляют участниками и правами через команды бота.

## Решения (согласовано)

- **Группа:** только по инвайт-ссылке (`/start join_{invite_code}`).
- **Имя в Чате:** спрашиваем у пользователя с припиской «латиницей»; простая
  валидация без кириллицы.
- **Одобрение:** любой ведущий из `group_facilitator` группы.
- **«Админ»** в UX = ведущий (`group_facilitator`).

## Предусловия

- Этапы 0–6 готовы (онбординг, facilitator-команды, `group_facilitator`).

## Задачи

1. **Модель** `membership_request` + поле `group.invite_code` (unique) + миграция.
   Backfill invite_code для существующих групп.
2. **Repo:** invite-код, заявки, approve/reject, deactivate member,
   add/remove facilitator (не снимать последнего ведущего).
3. **Сервис** `app/services/membership.py`: парсинг deep link, валидация имени,
   формат ссылок и текстов уведомлений.
4. **Роутер** `app/bot/routers/membership.py`:
   - `/start` для неизвестного chat_id: invite → подтверждение → имя → заявка;
   - pending → «ждём решения»; без invite → подсказка связаться с ведущим.
   - Callbacks ведущих: `mj:ok:{id}` / `mj:no:{id}` → создание `member` + уведомление.
   - `/group_invite` — ссылка-приглашение.
   - `/group_members` — список + «Сделать ведущим» / «Деактивировать».
   - `/group_requests` — ожидающие заявки.
5. **Онбординг** (существующий `/start` для участников в БД) — без изменений логики.
6. Команды в `commands.py`, справка в `help_text.py`, роутер в `main.py`.
7. `seed_member.py` — вывод invite_code; README + PROGRESS.

## Создаются/меняются файлы

`app/db/models.py`, `app/db/repo.py`, миграция Alembic,
`app/services/membership.py`, `app/bot/routers/membership.py`,
`app/bot/states.py`, `app/bot/keyboards.py`, `app/bot/command_names.py`,
`app/bot/commands.py`, `app/bot/help_text.py`, `app/bot/messages.py`,
`app/main.py`, `scripts/seed_member.py`, `tests/test_membership.py`,
`README.md`, `plan/PROGRESS.md`.

## Definition of Done

- Новый пользователь по invite → заявка → одобрение ведущим → `/start` → онбординг.
- Отклонение → сообщение пользователю; повторная заявка возможна.
- `/group_invite`, `/group_members`, `/group_requests` работают у ведущего.
- Назначение ведущего обновляет меню команд Telegram для этого chat_id.
- Seed и ручное добавление участника по-прежнему работают.

## Локальная проверка

1. Seed группы с ведущим A.
2. A: `/group_invite` → скопировать ссылку.
3. C: перейти по ссылке → имя латиницей → заявка.
4. A: «Принять» → C: `/start` → онбординг.
5. A: `/group_members` → назначить C ведущим; `/group_requests` при pending заявке.
6. Отклонить заявку — проверить сообщение заявителю.

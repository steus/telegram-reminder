# Трекер выполнения этапов

Отмечай этап выполненным только после прохождения «Definition of Done» и
«Локальной проверки» из его файла.

- [x] **Этап 0** — Каркас и инфраструктура (`stage-0-skeleton.md`)
- [ ] **Этап 1** — Онбординг и настройки (`stage-1-onboarding.md`)
- [ ] **Этап 2** — Задачи (ручной режим) (`stage-2-manual-tasks.md`)
- [ ] **Этап 3** — Чек-ин на кнопках (`stage-3-checkin.md`)
- [ ] **Этап 4** — LLM-слой и авто-извлечение (`stage-4-llm-extraction.md`)
- [ ] **Этап 5** — Декомпозиция и голос (`stage-5-decompose-voice.md`)
- [ ] **Этап 6** — Итоги и витрина (`stage-6-summary-sheets.md`)
- [ ] **Этап 7** — Прогресс и деплой (`stage-7-stats-deploy.md`)

## Заметки между этапами

> Сюда агент каждого этапа пишет короткие заметки для следующего: что отложено,
> известные TODO, неочевидные решения. 2–5 строк, без воды.

- **После этапа 0:** каркас собран и проверен (venv + alembic upgrade head + smoke
  test импортов/wiring). Таблицы `group`, `member`, `alembic_version` создаются.
  Enum'ы хранятся как VARCHAR (`native_enum=False`) — переносимо на Postgres.
  Миграции в Alembic используют `render_as_batch=True` (безопасный ALTER в SQLite).
- **Как завести тестового участника (для этапа 1):** сейчас в БД нет ни групп, ни
  участников. На этапе 1 нужен seed-скрипт `scripts/seed_member.py`: создать одну
  `group` (с `facilitator_chat_id`) и `member` со своим реальным Telegram chat_id,
  иначе `/start` ответит как незнакомцу. Узнать свой chat_id можно, временно
  залогировав `message.chat.id` в хендлере или через @userinfobot.
- **Env для разработки:** `.env` создаётся из `.env.example`; для smoke-теста
  выставлен placeholder `TELEGRAM_BOT_TOKEN=123:TEST` — заменить реальным токеном
  тест-бота перед запуском polling.

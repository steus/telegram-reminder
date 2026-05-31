# Трекер выполнения этапов

Отмечай этап выполненным только после прохождения «Definition of Done» и
«Локальной проверки» из его файла.

- [x] **Этап 0** — Каркас и инфраструктура (`stage-0-skeleton.md`)
- [x] **Этап 1** — Онбординг и настройки (`stage-1-onboarding.md`)
- [x] **Этап 2** — Задачи (ручной режим) (`stage-2-manual-tasks.md`)
- [x] **Этап 3** — Чек-ин на кнопках (`stage-3-checkin.md`)
- [x] **Этап 4** — LLM-слой и авто-извлечение (`stage-4-llm-extraction.md`)
- [x] **Этап 5** — Декомпозиция и голос (`stage-5-decompose-voice.md`)
- [x] **Этап 6** — Итоги и витрина (`stage-6-summary-sheets.md`)
- [x] **Этап 6b** — Вступление через Telegram (`stage-6b-member-join.md`)
- [ ] **Этап 7** — Прогресс и деплой (`stage-7-stats-deploy.md`)

## Бэклог (обсудить позже)

- **Web-UI для админов/ведущих** — управление группами, участниками, просмотр транскриптов
  и задач помимо Telegram. Детали (стек, роли, MVP) — отдельная проработка.

## Заметки между этапами

> Сюда агент каждого этапа пишет короткие заметки для следующего: что отложено,
> известные TODO, неочевидные решения. 2–5 строк, без воды.

- **После этапа 2:** модели `week`/`task`, private-поток через `/setgoals` → ввод
  текстом → экран подтверждения (`tk:ok`/`tk:ed`) → `confirmed=true`. `/tasks`
  показывает список со статусами. Парсинг в `structure_goals()` — точка расширения
  для LLM (этап 4). Миграция `44a7a5ae9877`.
- **После этапа 3:** планировщик — **одна минутная джоба** `minute_tick` (не per-member):
  в tz участника сверяет день/время чек-ина и (день+1)/время постановки задач.
  Дедуп слотов в `dialog_state.context_json.scheduler_sent`. Чек-ин: `app/services/checkin.py`,
  callback `t:{id}:{status}`, роутер `checkin`, `/checkin_now`. Затык — TODO в `on_stuck_status`.
  Постановка private — `app/services/goal_setup.py`. **Этап 4:** в ту же `_tick` ветку `auto`.
- **После этапа 4:** `app/llm/` — `ask_llm` + фолбэк (тест `tests/test_llm_fallback.py`).
  Plaud: `app/services/plaud.py` (API-каркас → scrape → ручная вставка). Транскрипт
  хранится в `week.transcript_text`; ведущий — `/set_plaud_url`, `/paste_transcript`,
  `/paste_done`, one-shot @-секции. Парсер «План действий»: `plaud_action_plan.py`
  (без LLM). Несколько ведущих: `group_facilitator`. Auto-поток:
  `app/services/auto_goal_setup.py`. Docker: `UID`/`GID` в `.env` для SQLite.
  Миграции `a1b2c3d4e5f6`, `b2c3d4e5f6a7`.
- **После этапа 5:** `app/services/voice.py` — whisper local/api, лимит
  `WHISPER_MAX_VOICE_DURATION`. Трекинг: `app/services/tracking.py` (промпт 2,
  маркер `[STATUSES]`). Декомпозиция: `decompose.py` + роутер `decompose`,
  callback `dc:yn:yes|no:{id}`, `dc:ok|ed:{id}`; шаги → `source=decomposed`,
  `week_id` следующей недели (`get_or_create_next_week`). **Whisper в Docker:**
  бинарь+модель монтируются томом (не в образ) — легче образ; на слабом VPS —
  `WHISPER_MODE=api`. Исправлен дубль `filter_extracted_tasks` в `extraction.py`.
- **После этапа 6:** `[REPORT_READY]` → `app/services/summary.py` (split, pending в
  `context_json`, кнопки `sm:yn:yes|no`). Маршрутизация по `visibility` → Sheets
  (`app/services/sheets.py`, только `group`), ведущим, или только БД. Модель
  `summary` + `SharedScope`. Миграция `c3d4e5f6a7b8`. `GOOGLE_SERVICE_ACCOUNT_JSON`.
- **После этапа 6b:** invite `/start join_{code}`, `membership_request`, роутер
  `membership.py`. Ведущий: `/group_invite`, `/group_members` (деактивировать/удалить),
  `/group_requests`. Callbacks `mj:*`. Миграция `d4e5f6a7b8c9`, `group.invite_code`.
  Фиксы: lazy-load группы в async (уведомления), парсинг `ob:tm:HH:MM`, подсказки `/help`.

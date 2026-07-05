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
- [x] **Этап 7** — Прогресс и деплой (`stage-7-stats-deploy.md`)
- [ ] **Этап 8** — Профиль участника: анкета JTBD (`stage-8-profile.md`)
  - [ ] 8A — анкета + профиль + подмешивание в разговорные ответы *(код готов; локальная проверка — на операторе)*
  - [ ] 8B — каскад целей год→квартал→неделя в промптах
  - [ ] 8C — таблица «Эксперименты» (лог гипотез)
  - [ ] 8D — анти-галлюцинационный контур (Tavily + верификатор + guard)

## Бэклог (обсудить позже)

- **Web-UI для админов/ведущих** — управление группами, участниками, просмотр транскриптов
  и задач помимо Telegram. Детали (стек, роли, MVP) — отдельная проработка.

## Критерии приёмки (§16 ТЗ)

- [x] `/start` — онбординг кнопками; незнакомому chat_id — вежливый отказ (6b + seed/invite).
- [x] Режим `auto` — извлечение из транскрипта с атрибуцией; фолбэк на ручную вставку.
- [x] Режим `private` — ввод текстом/голосом и структурирование.
- [x] Экран подтверждения задач до фиксации.
- [x] Чек-ин тапами, статусы в БД, редактирование сообщения.
- [x] `stuck` → предложение помощи; декомпозиция только по согласию.
- [x] Голос → текст (whisper local/api).
- [x] Итог сначала участнику; маршрутизация по `visibility`.
- [x] `/stats` — серия закрытых недель, % по неделям, частые stuck/decomposed.
- [x] LLM-фолбэк при ошибке основного провайдера.
- [x] Состояние диалога в БД, переживает рестарт.
- [ ] Смена `DATABASE_URL` на Postgres — схема переносима (enum VARCHAR), **локальный прогон на Postgres не выполнялся** в рамках этапа 7.
- [ ] Тестовый деплой на VPS — **артефакты готовы** (`docker-compose.prod.yml`, README); прогон на реальном VPS — на стороне оператора.

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
  callback `t:{id}:{status}`, роутер `checkin`, `/my_goals_update`. Затык — TODO в `on_stuck_status`.
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
- **После этапа 7:** `/stats` — `app/services/stats.py` + хендлер в `common.py`;
  midweek — `app/services/midweek.py`, слот `midweek` в `minute_tick` (день =
  встреча+3, время = `checkin_time`). Деплой: `docker-compose.prod.yml` (лимиты,
  логи), `deploy/bot-tracker.service`, `scripts/backup_db.sh`, README. Бэкап
  проверен локально (`./scripts/backup_db.sh`).
- **Этап 8A (в работе):** `member_profile` + `OnboardingStatus`, state
  `onboarding_survey`. Сервис `profile_onboarding.py` (JTBD-интервью, `[STATE]`/
  `[ПРОФИЛЬ_ГОТОВ]`, guard обязательных полей). Роутер `profile.py`, callback
  `pf:start|later|refill:*`. Профиль в `PROMPT_TRACKING`/`PROMPT_DECOMPOSE_STEPS`;
  nudge в чек-ине и декомпозиции. Миграция `e5f6a7b8c9d0`. Тесты
  `tests/test_profile_onboarding.py`.

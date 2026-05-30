# Трекер выполнения этапов

Отмечай этап выполненным только после прохождения «Definition of Done» и
«Локальной проверки» из его файла.

- [x] **Этап 0** — Каркас и инфраструктура (`stage-0-skeleton.md`)
- [x] **Этап 1** — Онбординг и настройки (`stage-1-onboarding.md`)
- [ ] **Этап 2** — Задачи (ручной режим) (`stage-2-manual-tasks.md`)
- [ ] **Этап 3** — Чек-ин на кнопках (`stage-3-checkin.md`)
- [ ] **Этап 4** — LLM-слой и авто-извлечение (`stage-4-llm-extraction.md`)
- [ ] **Этап 5** — Декомпозиция и голос (`stage-5-decompose-voice.md`)
- [ ] **Этап 6** — Итоги и витрина (`stage-6-summary-sheets.md`)
- [ ] **Этап 7** — Прогресс и деплой (`stage-7-stats-deploy.md`)

## Заметки между этапами

> Сюда агент каждого этапа пишет короткие заметки для следующего: что отложено,
> известные TODO, неочевидные решения. 2–5 строк, без воды.

- **После этапа 1:** онбординг через `/start` (кнопки: input_mode → visibility →
  weekday → time → ping). Состояние в `dialog_state.context_json` (`onboarded`,
  `step`, `settings_field`); `dialog_state.state` = `idle` во время онбординга.
  `/settings` — меню смены настроек (переиспользует те же клавиатуры).
  Seed: `python scripts/seed_member.py --chat-id CHAT_ID --name "Имя"`.
  Незнакомый chat_id → отказ без создания записи. Для живого теста нужен
  реальный `TELEGRAM_BOT_TOKEN` в `.env`.

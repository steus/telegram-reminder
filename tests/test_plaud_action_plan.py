"""Разбор Plaud «План действий»."""

from app.services.plaud_action_plan import count_action_plan_sections, extract_tasks_from_action_plan

SAMPLE = """
План действий


@Speaker 1

Провести КАСДЕВ (исследование клиента) с тремя людьми - [TBD]

Написать Денису с предложением пройти исследование - [TBD]



@Степан (Speaker 3)

Довести до конца вопросы с бухгалтерией - [TBD]

Связаться с клиенткой по поводу сайта для туристической компании - [TBD]

Сформулировать, какую конкретную пользу и решение бизнес-проблем он приносит клиентам - [TBD]

Проанализировать возможность автоматизации аудита сайтов с помощью ИИ - [TBD]

Изучить Reddit как потенциальный канал для привлечения клиентов и публикации контента - [TBD]

Связаться со Speaker 1 для консультации по ее сайту - [TBD]



@Майя (Speaker 4)

Потратить 6 часов на доработку сайта - [TBD]

Написать пост на тему "Почему я не могу получить это от ChatGPT" - [TBD]



@Speaker 2

Переработать бизнес-план по дата-центру, разбив его на три этапа - [TBD]
"""


def test_stepan_gets_only_his_section() -> None:
    tasks = extract_tasks_from_action_plan(SAMPLE, "Stepan")
    assert tasks is not None
    assert len(tasks) == 6
    assert tasks[0].startswith("Довести до конца вопросы")
    assert not any("КАСДЕВ" in t for t in tasks)
    assert not any("6 часов" in t for t in tasks)


def test_maya_section() -> None:
    tasks = extract_tasks_from_action_plan(SAMPLE, "Майя")
    assert tasks is not None
    assert len(tasks) == 2
    assert "6 часов" in tasks[0]


def test_speaker1_member_gets_speaker1_section() -> None:
    tasks = extract_tasks_from_action_plan(SAMPLE, "Speaker 1")
    assert tasks is not None
    assert len(tasks) == 2
    assert "КАСДЕВ" in tasks[0]


def test_stepan_not_matched_to_speaker1_section() -> None:
    tasks = extract_tasks_from_action_plan(SAMPLE, "Stepan")
    assert tasks is not None
    assert not any("КАСДЕВ" in t for t in tasks)


def test_plan_without_title_but_with_at_headers() -> None:
    text = """
@Степан (Speaker 3)

Довести до конца вопросы с бухгалтерией - [TBD]
"""
    tasks = extract_tasks_from_action_plan(text, "Stepan")
    assert tasks is not None
    assert len(tasks) == 1


def test_count_sections() -> None:
    assert count_action_plan_sections(SAMPLE) == 4
    assert count_action_plan_sections("@Speaker 1\n- one\n\n@Степан\n- two") == 2
    assert count_action_plan_sections("@Степан\n- only me") == 1

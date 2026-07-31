"""Разбор Plaud «План действий»."""

from app.services.plaud_action_plan import (
    count_action_plan_sections,
    extract_tasks_from_action_plan,
    list_unmatched_action_plan_headers,
    member_has_action_plan_section,
    merge_action_plan_transcripts,
)

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


def test_marina_header_matches_marina_member() -> None:
    text = "@Marina\nПровести мероприятие - [TBD]\n"
    assert member_has_action_plan_section(text, "Marina")
    tasks = extract_tasks_from_action_plan(text, "Marina")
    assert tasks == ["Провести мероприятие"]


def test_deniss_header_matches_denis_member() -> None:
    text = "@Deniss\nИзучить Твиттер - [TBD]\n"
    assert member_has_action_plan_section(text, "Denis")
    tasks = extract_tasks_from_action_plan(text, "Denis")
    assert tasks is not None
    assert len(tasks) == 1


def test_merge_action_plan_adds_second_participant() -> None:
    stepan = "@Stepan\nTask for Stepan - [TBD]"
    denis = "@Deniss\nTask for Denis - [TBD]"
    merged = merge_action_plan_transcripts(stepan, denis)
    assert member_has_action_plan_section(merged, "Stepan")
    assert member_has_action_plan_section(merged, "Denis")
    assert extract_tasks_from_action_plan(merged, "Stepan") == ["Task for Stepan"]
    assert extract_tasks_from_action_plan(merged, "Denis") == ["Task for Denis"]


def test_merge_action_plan_updates_existing_section() -> None:
    existing = "@Deniss\nOld task - [TBD]"
    updated = "@Deniss\nNew task - [TBD]\nAnother task - [TBD]"
    merged = merge_action_plan_transcripts(existing, updated)
    tasks = extract_tasks_from_action_plan(merged, "Denis")
    assert tasks == ["New task", "Another task"]


MARINA_PLAN = """План дейсвий
@Denisskud
-  Провести созвон со Speaker 2 для завершения разработки и тестирования бота
-  Опубликовать написанную статью в LinkedIn
-  Проверить составленный Мариной текст вакансии ассистента и дать обратную связь
@StepanTeus
-  Провести созвон со Deniss Kudrjashov для завершения разработки и тестирования бота
-  Протестировать готового бота
-  Проверить составленный Мариной текст вакансии ассистента и дать обратную связь
-  Попробовать связаться с «полутеплым» клиентом по поводу небольшого проекта
@Marina_Bussines
-  Выбрать кандидата на позицию ассистента и выдать ему тестовое задание сроком на одну неделю
-  Разместить объявление о найме ассистента на CV Keskus и в профильных Facebook-группах
-  Простроить воронку и отснять контент до 14 августа, завершив работу до 2 августа
-  Подготовить и провести краткую самопрезентацию на встрече с предпринимателями, используя утвержденную формулировку
@MayaMich
-  Провести повторные переговоры с Ирой по выбору места для мастер-класса по коммуникациям (квартал Вольта или «Русалка»)
-  Анонсировать курс по лидерскому PCM на мастер-классе 30 июля и предложить запись
"""


def test_marina_plan_splits_four_sections() -> None:
    assert count_action_plan_sections(MARINA_PLAN) == 4
    assert len(extract_tasks_from_action_plan(MARINA_PLAN, "Denis") or []) == 3
    assert len(extract_tasks_from_action_plan(MARINA_PLAN, "Stepan Teus") or []) == 4
    assert len(extract_tasks_from_action_plan(MARINA_PLAN, "Marina") or []) == 4
    assert len(extract_tasks_from_action_plan(MARINA_PLAN, "Maya Mich") or []) == 2
    assert not any(
        "LinkedIn" in t
        for t in (extract_tasks_from_action_plan(MARINA_PLAN, "Stepan Teus") or [])
    )


def test_zwsp_before_headers_does_not_collapse_sections() -> None:
    broken = (
        "План действий\n"
        "@Denisskud\n-  D1\n-  D2\n-  D3\n"
        "\u200b@StepanTeus\n-  S1\n-  S2\n-  S3\n-  S4\n"
        "\ufeff@Marina_Bussines\n-  M1\n-  M2\n"
        "\u200e@MayaMich\n-  Y1\n-  Y2\n"
    )
    assert count_action_plan_sections(broken) == 4
    assert extract_tasks_from_action_plan(broken, "Denis") == ["D1", "D2", "D3"]
    assert extract_tasks_from_action_plan(broken, "Stepan Teus") == [
        "S1",
        "S2",
        "S3",
        "S4",
    ]


def test_fullwidth_at_is_normalized() -> None:
    text = "＠StepanTeus\n-  Task one\n"
    assert extract_tasks_from_action_plan(text, "Stepan") == ["Task one"]


def test_list_unmatched_headers() -> None:
    unmatched = list_unmatched_action_plan_headers(
        MARINA_PLAN, ["Stepan Teus", "Marina"]
    )
    assert "Denisskud" in unmatched
    assert "MayaMich" in unmatched
    assert "StepanTeus" not in unmatched
    assert "Marina_Bussines" not in unmatched


def test_no_title_needed_only_at_headers() -> None:
    text = "@Alexey\n- First task\n\n@Ольга\n- Second task\n"
    assert count_action_plan_sections(text) == 2
    assert extract_tasks_from_action_plan(text, "Alexey") == ["First task"]
    assert extract_tasks_from_action_plan(text, "Ольга") == ["Second task"]


def test_translit_matches_without_name_whitelist() -> None:
    """Кириллица↔латиница через транслит, не через список имён группы."""
    text = "@NikitaVolkov\n- Ship the release\n"
    assert extract_tasks_from_action_plan(text, "Никита Волков") == ["Ship the release"]
    assert member_has_action_plan_section(text, "Никита")


def test_extract_tasks_for_header() -> None:
    from app.services.plaud_action_plan import extract_tasks_for_header

    tasks = extract_tasks_for_header(MARINA_PLAN, "StepanTeus")
    assert len(tasks) == 4
    assert "Протестировать готового бота" in tasks

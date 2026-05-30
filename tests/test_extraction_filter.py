"""Фильтр чужих задач после LLM."""

from app.services.extraction import filter_extracted_tasks


def test_filter_speaker_line_as_assignee() -> None:
    tasks = ["Speaker 1: доработать сайт", "Связаться с клиентом"]
    result = filter_extracted_tasks(tasks, "Stepan", ["Denis"])
    assert result == ["Связаться с клиентом"]


def test_filter_other_member_as_subject() -> None:
    tasks = ["Denis проведет три KASDEV-интервью", "Stepan свяжется с бухгалтерией"]
    result = filter_extracted_tasks(tasks, "Stepan", ["Denis"])
    assert result == ["Stepan свяжется с бухгалтерией"]


def test_keep_contact_other_person() -> None:
    tasks = ["Написать Денису с предложением пройти KASDEV"]
    result = filter_extracted_tasks(tasks, "Stepan", ["Denis"])
    assert tasks == result

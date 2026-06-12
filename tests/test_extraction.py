"""Разбор ручного ввода задач."""

from app.services.extraction import parse_manual_input


def test_parse_manual_input_keeps_chernovik_in_task_text() -> None:
    text = (
        "Изучить и начать вести Твиттер, а также подготовить рассказ для группы "
        "по результатам первых шагов (черновик)\n"
        "Написать отзыв «своему бухгалтеру» (черновик)\n"
        "проверить бота"
    )
    tasks = parse_manual_input(text)
    assert len(tasks) == 3
    assert "(черновик)" in tasks[0]
    assert "(черновик)" in tasks[1]
    assert tasks[2] == "проверить бота"

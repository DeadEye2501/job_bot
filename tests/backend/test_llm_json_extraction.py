"""Следствия вырезания ответа-объекта из того, что вернула модель.

Модель редко отвечает одним голым объектом: перед ним бывает рассуждение,
после — извинения или повтор. Берётся последний найденный объект: если модель
сперва показала пример из промпта, а потом дала ответ, ответом будет второе.

Кавычки, которые редакторы и модели ставят «ёлочками» и «лапками», приводятся
к прямым до разбора — иначе разбор JSON падает на своей же кавычке.
"""

import json
import logging

import pytest

from backend.llm.answers import extract_last_json, json_object, log_unparseable


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param('{"a": 1}', '{"a": 1}', id="голый объект"),
        pytest.param(
            'Вот ответ: {"a": 1}. Надеюсь, помог.',
            '{"a": 1}',
            id="объект среди текста",
        ),
        pytest.param(
            'Пример: {"a": 1}\nОтвет: {"a": 2}',
            '{"a": 2}',
            id="берётся последний из двух",
        ),
        pytest.param("", None, id="пустой ответ"),
        pytest.param("совсем без объекта", None, id="объекта нет"),
        pytest.param('{"a": 1', None, id="скобка не закрыта"),
    ],
)
def test_the_last_object_is_taken_from_the_answer(answer, expected):
    """Из ответа берётся последний объект, а без объекта — ничего."""
    assert extract_last_json(answer) == expected


def test_the_text_as_it_came_is_tried_before_the_straightened_one():
    """Сначала разбирается текст как есть, и только потом выпрямленный.

    Выпрямление заведено ради моделей, ставящих ёлочки вместо кавычек
    JSON, но те же ёлочки встречаются и внутри значений по-русски.
    Начни мы с выпрямленного — и годный объект уступил бы место тому,
    который стал разбираемым только после подмены кавычек.
    """
    answer = 'Сначала: {"a": 1}\nПотом: {“b”: 2}'

    assert extract_last_json(answer) == '{"a": 1}'


def test_the_last_scrap_is_returned_when_nothing_parses():
    """Когда не разбирается ничто, отдаётся последний огрызок.

    Зовущий сообщит о неразбираемом ответе одинаково при любом из них,
    но правило то же, что и у разбираемых: ответ модели дописывается в
    конце, и последнее слово за ним.
    """
    answer = 'Черновик: {"a": 1,}\nОтвет: {"b": 2,}'

    assert extract_last_json(answer) == '{"b": 2,}'


def test_curly_quotes_are_straightened_before_the_search():
    """Кавычки-ёлочки и лапки выпрямляются до поиска объекта.

    Модель, отвечающая по-русски, ставит их сама, и разбор падал бы на
    первой же такой кавычке.
    """
    assert extract_last_json('{“a”: ‘b’}') == '{"a": \'b\'}'


def test_a_nested_object_is_not_matched():
    """Вложенный объект целиком не выхватывается.

    Выражение ищет объект без вложенных скобок, поэтому у ответа с
    вложенностью совпадёт только внутренняя часть. Тест закрепляет
    сегодняшнее поведение: разбор такого ответа даст не то, что ждали.
    """
    assert extract_last_json('{"outer": {"inner": 1}}') == '{"inner": 1}'



def test_typographic_quotes_inside_a_value_do_not_break_the_object():
    """Объект с кавычками-ёлочками внутри значения остаётся читаемым.

    Выпрямление кавычек заведено ради моделей, которые ставят ёлочки вместо
    кавычек JSON. Но в тексте ответа они встречаются и по-русски: выпрямив их
    внутри значения, мы ломаем годный объект и теряем ответ модели целиком.
    """
    answer = '{"reasoning": "“Сбер” и ПАО Сбербанк — одно"}'

    assert json.loads(extract_last_json(answer)) == {
        "reasoning": "“Сбер” и ПАО Сбербанк — одно"
    }

def test_an_unreadable_answer_leaves_a_trace_in_the_log(caplog):
    """Ответ, из которого объект не собрался, оставляет след в журнале.

    Наружу неудача уходит откатом: у одного зовущего пусто, у другого пара с
    причиной, у третьего «пропускаем». Двое из пятерых при этом молчат совсем,
    и без этой записи разбирать, почему модель перестала отвечать объектом,
    было бы нечем.
    """
    with caplog.at_level(logging.DEBUG, logger="проверка"):
        assert json_object("я не понял", logging.getLogger("проверка"), "разбор") is None

    assert any(rec.name == "проверка" for rec in caplog.records)

def test_a_complaint_about_an_unparsed_answer_names_the_purpose(caplog):
    """Громкая жалоба на неразобранный ответ называет обращение и показывает
    оба края ответа.

    Четверо зовущих писали её своими руками, и трое не обрезали ответ вовсе —
    разбор резюме уезжал в журнал целиком. Обрезка при этом не может быть
    только по началу: у рассуждающей модели начало занято размышлением, а
    объект, из-за которого всё и сломалось, лежит в конце.
    """
    answer = "начало" + "ш" * 900 + "конец"

    with caplog.at_level(logging.WARNING, logger="проверка"):
        log_unparseable(answer, logging.getLogger("проверка"), "разбор вакансии")

    written = [
        rec.getMessage() for rec in caplog.records if rec.name == "проверка"
    ]
    assert len(written) == 1
    assert "разбор вакансии" in written[0]
    assert "начало" in written[0] and "конец" in written[0]
    assert "ш" * 900 not in written[0]


def test_an_object_that_will_not_parse_yields_nothing(caplog):
    """Похожее на объект, но неразбираемое даёт отсутствие, а не падение.

    Модель отвечает и так: скобки на месте, а внутри оборванная строка или
    висящая запятая. Зовущий на такое обязан получить свой откат, а не
    исключение посреди разбора.
    """
    with caplog.at_level(logging.DEBUG, logger="проверка"):
        answer = json_object(
            '{"verdict": "ok",}', logging.getLogger("проверка"), "разбор"
        )

    assert answer is None
    assert any(rec.exc_info for rec in caplog.records if rec.name == "проверка")


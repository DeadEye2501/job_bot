"""Следствия, которые наблюдают тесты `backend/domain/salary.py`.

Разбор ничего не пересчитывает: из строки достаётся число, как оно в ней
записано, и валюта, если названа. Приведение к одной валюте было бы враньём —
курс в объявлении не указан, а отбор в списке идёт по написанному числу.

Проверяется не точность подсчёта, а то, что число не разваливается на
разрядах, суффикс тысяч раскрывается, а мусор не превращается в зарплату.
"""

import pytest

from backend.domain.salary import parse_salary
from backend.models import Currency


@pytest.mark.parametrize("raw", [None, "", "   ", "—"])
def test_nothing_is_extracted_from_a_blank_salary(raw):
    """Из пустой строки не берётся ни число, ни валюта."""
    assert parse_salary(raw) == (None, None, None)


def test_a_negotiable_salary_yields_no_range_despite_stray_numbers():
    """«По итогам собеседования» — не зарплата, даже если рядом есть числа."""
    assert parse_salary("по итогам собеседования, 30 дней отпуска") == (
        None,
        None,
        None,
    )


def test_a_rouble_range_is_kept_as_written():
    """Рублёвый диапазон остаётся тем же числом, каким записан."""
    assert parse_salary("150 000 — 300 000 ₽") == (150000, 300000, Currency.RUB)


def test_a_space_inside_a_number_does_not_break_it():
    """Пробел-разделитель разрядов не разрывает число надвое.

    Написание «$3 000» встречается в объявлениях наравне с «$3000», и разрыв
    на «3» и «000» превращал бы три тысячи долларов в диапазон от нуля до трёх.
    """
    assert parse_salary("$3 000") == (3000, 3000, Currency.USD)


def test_a_currency_amount_is_not_converted():
    """Валютное число не умножается ни на какой курс."""
    assert parse_salary("$3000-5000") == (3000, 5000, Currency.USD)


def test_a_single_number_gives_equal_bounds():
    """Одно число — диапазон из самого себя."""
    assert parse_salary("200000 ₽") == (200000, 200000, Currency.RUB)


@pytest.mark.parametrize("raw", ["300K", "300 тыс"])
def test_a_thousands_marker_is_expanded(raw):
    """Пометка тысяч раскрывается в число целиком."""
    assert parse_salary(raw) == (300000, 300000, None)


def test_a_cyrillic_thousands_marker_works_too():
    """Пометка тысяч кириллицей читается наравне с латинской."""
    assert parse_salary("от 250к до 400к ₽") == (250000, 400000, Currency.RUB)


def test_a_millions_marker_is_expanded_too():
    """«5 млн» — это пять миллионов, а не пять."""
    assert parse_salary("5 млн ₽") == (5000000, 5000000, Currency.RUB)


def test_bare_numbers_are_taken_at_face_value():
    """Голое число берётся как написано, без догадок о единицах."""
    assert parse_salary("1500-3000") == (1500, 3000, None)


def test_the_bounds_come_back_sorted():
    """Границы возвращаются по возрастанию независимо от порядка в строке."""
    assert parse_salary("300 000 — 150 000 ₽") == (150000, 300000, Currency.RUB)


@pytest.mark.parametrize(
    "raw, currency",
    [
        ("3000 долларов", Currency.USD),
        ("3000 USD", Currency.USD),
        ("2000 евро", Currency.EUR),
        ("2000 EUR", Currency.EUR),
        ("150000 руб.", Currency.RUB),
        ("150000 RUB", Currency.RUB),
    ],
)
def test_the_currency_is_recognised_by_word_as_well_as_by_sign(raw, currency):
    """Валюта опознаётся и знаком, и словом, и кодом."""
    assert parse_salary(raw)[2] is currency


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("оклад 100 000 ₽ + KPI", 100000),
        ("150000 ₽, Краснодар", 150000),
        ("150 000 ₽, пишите рекрутеру", 150000),
        ("$3000 per month", 3000),
        ("3000 USD/mo", 3000),
        ("$3000 monthly", 3000),
    ],
)
def test_a_letter_inside_a_word_is_not_a_thousands_marker(raw, expected):
    """Пометка тысяч и миллионов считается только своей у числа.

    «K» в «KPI», «к» в «Краснодаре», «m» в «month» — обычные буквы соседнего
    слова. Пока множитель искали по всей строке, любое из них умножало
    зарплату на тысячу или на миллион.
    """
    assert parse_salary(raw)[:2] == (expected, expected)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$3,000", (3000, 3000)),
        ("150,000 - 300,000 RUB", (150000, 300000)),
    ],
)
def test_a_comma_between_thousands_does_not_break_the_number(raw, expected):
    """Запятая-разделитель разрядов не разрывает число.

    Английское «$3,000» распадалось на «3» и «000», и три тысячи долларов
    превращались в три.
    """
    assert parse_salary(raw)[:2] == expected


@pytest.mark.parametrize("raw", ["3.5к", "3,5к"])
def test_a_fraction_is_one_number_and_not_a_range(raw):
    """Дробное число остаётся одним числом, а не парой границ."""
    assert parse_salary(raw)[:2] == (3500, 3500)


def test_numbers_separated_by_a_line_break_stay_apart():
    """Перенос строки числа не склеивает."""
    assert parse_salary("150000\n200000")[:2] == (150000, 200000)


def test_a_percentage_is_not_a_salary():
    """Процент премии в границы зарплаты не попадает."""
    assert parse_salary("200 000 ₽ + KPI до 20%") == (200000, 200000, Currency.RUB)


def test_a_zero_bound_is_dropped():
    """Ноль зарплатой не бывает и нижней границей не становится."""
    assert parse_salary("от 0 до 300 000 ₽") == (300000, 300000, Currency.RUB)


@pytest.mark.parametrize(
    "raw", ["по трудовому договору, 200 000 ₽", "200 000 ₽, оформление по договору ГПХ"]
)
def test_a_contract_mention_does_not_hide_a_named_salary(raw):
    """Слово «договор» само по себе зарплату не отменяет.

    Отменяет её только «по договорённости»: там суммы нет вовсе, а «трудовой
    договор» и «договор ГПХ» стоят рядом с прямо названной суммой.
    """
    assert parse_salary(raw)[:2] == (200000, 200000)


@pytest.mark.parametrize(
    "raw",
    [
        "по договорённости",
        "зарплата договорная",
        "по договорённости, вилка от 100 000 до 200 000 ₽",
    ],
)
def test_a_salary_left_to_agreement_yields_nothing(raw):
    """«По договорённости» — не зарплата, даже когда рядом названы числа.

    Числа при ней означают не вилку, а что угодно: прошлый оклад, порог
    рынка, диапазон по грейдам. Брать их за зарплату — врать отбору.
    """
    assert parse_salary(raw) == (None, None, None)


def test_a_currency_name_inside_a_word_is_not_the_currency():
    """«Европе» — не евро, и рублёвую вакансию в евро не превращает."""
    assert parse_salary("работа в Европе, 150000 руб")[2] is Currency.RUB


def test_two_currencies_at_once_leave_the_currency_unknown():
    """Когда названы две валюты, догадка запрещена.

    Диапазон «от 1000 $ до 2000 €» не имеет смысла ни в одной из них, и
    выбирать первую попавшуюся — значит прятать вакансию от отбора по второй.
    """
    assert parse_salary("от 1000 $ до 2000 €")[2] is None


def test_an_unnamed_currency_stays_unknown():
    """Не названная в строке валюта не додумывается.

    Догадка «раз без знака, значит рубли» отправила бы долларовую вакансию,
    записанную без знака, в рублёвую выдачу.
    """
    assert parse_salary("от 150000 до 200000")[2] is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$1,000.50", 1000),
        ("€3.000,50", 3000),
        ("150.000,00 руб", 150000),
    ],
)
def test_a_number_with_both_separators_is_read_and_does_not_blow_up(raw, expected):
    """Разряды и дробная часть в одном числе разбираются, а не роняют разбор.

    Написание «$1,000.50» — обычное английское. Пока десятичный знак и
    разделитель разрядов не были разведены, такое число не просто читалось
    неверно — оно бросало, а вылетевший разбор оставлял вакансию
    неразобранной навсегда: конвейер брал её заново при каждом запуске.
    """
    assert parse_salary(raw)[:2] == (expected, expected)


@pytest.mark.parametrize("space", [" ", " ", " "])
def test_a_typographic_space_inside_a_number_does_not_break_it(space):
    """Неразрывный и узкий пробелы внутри числа читаются наравне с обычным.

    Именно их ставит типографика, и именно они приезжают из объявлений
    Telegram. Обычный пробел в такой строке — скорее исключение.
    """
    assert parse_salary(f"200{space}000 ₽") == (200000, 200000, Currency.RUB)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("300 тысяч ₽", 300000),
        ("300 тыс. ₽", 300000),
        ("1 миллион рублей", 1000000),
    ],
)
def test_a_marker_written_out_in_full_is_a_marker_too(raw, expected):
    """Пометка, написанная словом целиком, читается наравне с сокращением."""
    assert parse_salary(raw)[:2] == (expected, expected)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("150-200 тыс руб", (150000, 200000)),
        ("от 100 до 150 к", (100000, 150000)),
        ("зарплата 100 — 150 тыс", (100000, 150000)),
    ],
)
def test_a_marker_at_the_end_of_a_range_covers_the_whole_range(raw, expected):
    """Пометка в конце вилки относится ко всей вилке, а не к одному числу.

    «150-200 тыс» — это сто пятьдесят и двести тысяч. Пока пометка
    доставалась только своему числу, в одну строку ложились сто пятьдесят
    рублей и двести тысяч рублей разом.
    """
    assert parse_salary(raw)[:2] == expected


def test_years_of_experience_do_not_become_a_salary_bound():
    """В «300к, опыт от 5 лет» пять — это годы, а не нижняя граница.

    Пока в границы шли все числа строки, вакансия с таким описанием попадала
    в выдачу по отбору «зарплата от 5» и показывала в карточке вилку
    «от 5 до 300 000».
    """
    assert parse_salary("300к, опыт от 5 лет")[:2] == (300000, 300000)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("премия 50 000 ₽, оклад 150 000 ₽", (150000, 150000)),
        ("5 лет опыта — зарплата 300к", (300000, 300000)),
        ("опыт от 3, зарплата 200 000 ₽", (200000, 200000)),
        ("100 000 – 150 000 ₽, релокация 300 000 ₽", (100000, 150000)),
    ],
)
def test_the_bounds_come_from_the_first_range_that_is_about_money(raw, expected):
    """Границы берутся у первой связки, в которой речь о деньгах.

    Четыре написания, на которых правило видно порознь: примета слева от
    числа, примета справа, примета через предлог и вторая денежная связка,
    которая в границы уже не идёт.
    """
    assert parse_salary(raw)[:2] == expected


def test_a_currency_sign_inside_a_range_does_not_cut_it_in_half():
    """Знак валюты у каждой границы вилку не разрывает.

    «от 150 000 ₽ до 250 000 ₽» — обычное написание, и верхняя граница в нём
    не должна пропадать: с потерянным верхом отбор «зарплата от 200 000»
    прячет вакансию, которая под него подходит.
    """
    assert parse_salary("от 150 000 ₽ до 250 000 ₽")[:2] == (150000, 250000)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("150 000 - 200 000 руб 2 года", (150000, 200000)),
        ("100 000 руб. 3 года опыта", (100000, 100000)),
    ],
)
def test_a_currency_word_does_not_drag_a_stray_number_into_the_range(raw, expected):
    """Слово валюты не приклеивает к вилке постороннее число.

    Знак валюты пишут у каждой границы, поэтому он входит в склейку вилки —
    но только вместе с тире или «до». Иначе «200 000 руб 2 года» слипается в
    одну связку, примета «года» отбраковывает её целиком, и вакансия
    остаётся вовсе без зарплаты — хуже, чем с неверной нижней границей.
    """
    assert parse_salary(raw)[:2] == expected


def test_a_yearly_pay_written_as_a_year_is_still_a_pay():
    """«1 500 000 год» — годовая зарплата, а не срок.

    Приметой служат «года» и «лет», но не «год»: после суммы это слово
    говорит, за какой срок её платят.
    """
    assert parse_salary("1 500 000 год")[:2] == (1500000, 1500000)


def test_a_bonus_written_after_the_pay_does_not_hide_the_pay():
    """Слово «бонус» вводит следующее число, а не отменяет предыдущее.

    В «оклад 200 000 бонус 50 000» двести тысяч — это оклад, и строка не
    должна оставаться вовсе без зарплаты.
    """
    assert parse_salary("оклад 200 000 бонус 50 000")[:2] == (200000, 200000)


def test_a_hyphenated_years_form_is_still_years():
    """«от 3-х лет» — тоже срок, хотя написано через дефис.

    Написание с наращением встречается наравне с голым числом, и стаж в нём
    не должен подменять собой вилку, названную в той же строке.
    """
    assert parse_salary("стаж работы от 3-х лет, зарплата 250 000")[:2] == (
        250000,
        250000,
    )


def test_a_yearly_pay_is_still_a_pay():
    """«300 000 годовых» — зарплата, а не срок.

    Приметы не-денег ищутся по корню слова, и корень «год» задевает не только
    срок работы, но и то, как часто её платят. Строка с таким написанием
    теряла сумму целиком.
    """
    assert parse_salary("300 000 годовых")[:2] == (300000, 300000)


def test_a_bonus_beside_the_pay_does_not_become_the_lower_bound():
    """Премия рядом с окладом — не нижняя граница зарплаты.

    «фикс 150 000 ₽, бонус 50 000 ₽» — это оклад в сто пятьдесят тысяч.
    Пятьдесят тысяч нижней границей отдавали вакансию отбору «от 50 000» и
    прятали её от отбора «от 100 000», под который она подходит.
    """
    assert parse_salary("фикс 150 000 ₽, бонус 50 000 ₽")[:2] == (150000, 150000)


def test_the_pay_is_found_when_the_experience_is_written_first():
    """Требование опыта, стоящее перед вилкой, её не подменяет.

    Порядок в объявлении бывает любым, и брать первое попавшееся число
    нельзя: в «опыт от 5 лет, зарплата от 300к» первое число — годы.
    """
    assert parse_salary("опыт от 5 лет, зарплата от 300к")[:2] == (300000, 300000)


def test_a_number_too_big_for_the_column_is_dropped():
    """Число, не влезающее в колонку, зарплатой не считается.

    Модель пишет строку зарплаты дословно, и в неё попадает что угодно —
    например, слипшийся ряд цифр. Записать такое значит уронить разбор
    вакансии на коммите и оставить её неразобранной навсегда.
    """
    assert parse_salary("1234567890123456789012345 ₽") == (None, None, None)

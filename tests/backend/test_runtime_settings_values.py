"""Следствия типизированных свойств `RuntimeSettings`.

Свойства читают общий словарь ключ-значение и приводят его к типу, подставляя
умолчания. Значения сняты прогоном настоящих свойств.
"""

import pytest

from backend.runtime_settings import RuntimeSettings


def settings(**app) -> RuntimeSettings:
    """Настройки с заданным словарём в памяти, минуя базу.

    Помощник кладёт значения прямо в закрытое поле, и это осознанно. Дорога
    «строка в базе → чтение → словарь» проверена отдельно, в тестах чтения:
    там есть и настройка, доехавшая до свойства, и пустое значение,
    прочитанное как «не задано». Здесь проверяется другое — приведение к
    типу, умолчания и зажимы, — и гонять ради каждого случая базу значило бы
    двадцать раз перепроверять уже проверенный провод.

    Фабрика сессий намеренно не передана: свойства до базы доходить не
    должны, и если какое-то дойдёт, тест упадёт на `None`.
    """
    made = RuntimeSettings(None)
    made._app = dict(app)
    return made


def test_a_missing_key_falls_back_to_the_default():
    """Отсутствующий ключ отдаёт умолчание."""
    assert settings().scoring_threshold == 10


@pytest.mark.parametrize("raw", ["", "   "])
def test_a_blank_value_counts_as_not_set(raw):
    """Пустое значение и одни пробелы — это «не задано»."""
    assert settings(scoring_threshold=raw).scoring_threshold == 10


def test_a_stored_value_wins_over_the_default():
    """Заданное значение сильнее умолчания."""
    assert settings(scoring_threshold="42").scoring_threshold == 42


def test_surrounding_spaces_do_not_break_a_value():
    """Пробелы вокруг значения не мешают его прочитать."""
    assert settings(scoring_threshold="  42  ").scoring_threshold == 42


@pytest.mark.parametrize("raw", ["true", "True", "TRUE", "  true  "])
def test_a_switch_is_on_for_any_spelling_of_true(raw):
    """Переключатель включён при любом написании слова «true»."""
    assert settings(wizard_completed=raw).wizard_completed is True


@pytest.mark.parametrize("raw", ["false", "yes", "1", ""])
def test_anything_but_true_leaves_a_switch_off(raw):
    """Всё остальное оставляет переключатель выключенным — включая «yes» и «1»."""
    assert settings(wizard_completed=raw).wizard_completed is False


@pytest.mark.parametrize(
    "key, expected",
    [("poll_interval_sec", 1800), ("backfill_limit", 15), ("dm_backfill_limit", 50)],
)
def test_a_missing_whole_number_setting_falls_back_to_its_default(key, expected):
    """У целочисленных настроек опроса и бэкафилла есть умолчание."""
    assert getattr(settings(), key) == expected


@pytest.mark.parametrize(
    "key", ["poll_interval_sec", "backfill_limit", "dm_backfill_limit"]
)
def test_a_written_whole_number_setting_is_read_back(key):
    """Записанное число читается обратно — в этом смысл настройки.

    Значение подобрано отличным от всех умолчаний нарочно: совпади оно с
    любым из них, «прочитали записанное» было бы неотличимо от «не
    прочитали вовсе».
    """
    assert getattr(settings(**{key: "7"}), key) == 7


@pytest.mark.parametrize(
    "key", ["poll_interval_sec", "backfill_limit", "dm_backfill_limit"]
)
def test_a_written_whole_number_survives_stray_spaces(key):
    """Пробелы вокруг числа не мешают его прочесть.

    Настройки правят руками через просмотрщик базы, и лишний пробел там
    появляется сам собой.
    """
    assert getattr(settings(**{key: "  7  "}), key) == 7


def test_sending_is_locked_until_explicitly_allowed():
    """Отправка заперта по умолчанию: пустая база не разрешает слать в Telegram."""
    assert settings().send_locked is True


def test_sending_unlocks_once_explicitly_allowed():
    """Записанное «false» действительно снимает запор — в этом смысл настройки."""
    assert settings(send_locked="false").send_locked is False


def test_automatic_apply_is_on_by_default():
    """Автоматическая отправка откликов по умолчанию включена."""
    assert settings().auto_apply is True


def test_automatic_apply_turns_off_when_set():
    """Записанное «false» отключает авто-отправку откликов."""
    assert settings(auto_apply="false").auto_apply is False


@pytest.mark.parametrize(
    "raw, expected",
    [("0.92", 0.92), ("0.999", 0.999), ("0.5", 0.5)],
)
def test_a_threshold_inside_the_range_is_kept(raw, expected):
    """Порог дедупа в пределах допустимого берётся как есть."""
    assert settings(dedup_cosine_threshold=raw).dedup_cosine_threshold == expected


def test_a_threshold_below_the_floor_is_raised_to_it():
    """Слишком низкий порог поднимается: иначе всё подряд считалось бы дублем."""
    assert settings(dedup_cosine_threshold="0.3").dedup_cosine_threshold == 0.5


def test_a_threshold_above_the_ceiling_is_lowered_to_it():
    """Слишком высокий опускается: иначе дедуп выключился бы совсем."""
    assert settings(dedup_cosine_threshold="1.5").dedup_cosine_threshold == 0.999


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "не число", ""])
def test_an_unusable_threshold_falls_back_to_the_baseline(raw):
    """Негодный порог заменяется опорным значением, а не роняет разбор."""
    assert settings(dedup_cosine_threshold=raw).dedup_cosine_threshold == 0.92


def test_a_stored_currency_rate_is_used():
    """Заданный курс берётся из настроек."""
    assert settings(salary_usd_to_rub="95").salary_usd_to_rub == 95


def test_a_stored_eur_currency_rate_is_used():
    """Заданный курс евро берётся из настроек, а не только доллара."""
    assert settings(salary_eur_to_rub="105").salary_eur_to_rub == 105


@pytest.mark.parametrize("raw", ["0", "-5", "не число", ""])
def test_an_unusable_currency_rate_falls_back_to_the_default(raw):
    """Ноль, отрицательное и мусор заменяются умолчанием: курс не бывает таким."""
    assert settings(salary_usd_to_rub=raw).salary_usd_to_rub == 90
    assert settings(salary_eur_to_rub=raw).salary_eur_to_rub == 100


def test_a_stored_flood_window_is_read_as_a_moment_in_time():
    """Окно ожидания после флуда читается дробным числом."""
    got = settings(flood_wait_until_ts="1700000000.5").flood_wait_until_ts

    assert got == 1700000000.5


@pytest.mark.parametrize("raw", ["не число", ""])
def test_an_unusable_flood_window_means_no_wait(raw):
    """Негодное окно означает «ждать не надо», а не падение."""
    assert settings(flood_wait_until_ts=raw).flood_wait_until_ts == 0.0


@pytest.mark.parametrize(
    ("key", "default"),
    [
        ("scoring_threshold", 10),
        ("poll_interval_sec", 1800),
        ("backfill_limit", 15),
        ("dm_backfill_limit", 50),
    ],
)
@pytest.mark.parametrize("raw", ["не число", "1 800"])
def test_a_garbled_whole_number_setting_falls_back_to_its_default(key, default, raw):
    """Мусор в целочисленной настройке откатывается к умолчанию.

    Значения правят руками через DBeaver, и опечатка вроде «1 800» роняла
    приложение на старте — при том, что соседние числовые настройки, курсы
    валют и порог дедупа, такое переживают откатом.
    """
    assert getattr(settings(**{key: raw}), key) == default


def test_the_path_to_the_resume_is_empty_until_set():
    """Путь к резюме пуст, пока его не задали."""
    assert settings().cv_path == ""


def test_a_stored_resume_path_is_used():
    """Заданный путь к резюме берётся из настроек."""
    assert settings(cv_path="/tmp/cv.pdf").cv_path == "/tmp/cv.pdf"

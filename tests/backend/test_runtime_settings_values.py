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
    assert settings().scoring_threshold == 5


@pytest.mark.parametrize("raw", ["", "   "])
def test_a_blank_value_counts_as_not_set(raw):
    """Пустое значение и одни пробелы — это «не задано»."""
    assert settings(scoring_threshold=raw).scoring_threshold == 5


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


def test_sending_is_open_until_explicitly_locked():
    """Отправка по умолчанию настоящая: пустая база не включает симуляцию.

    Симуляция — это отладочный стенд, а не состояние, в котором приложением
    пользуются: включённая молча, она показывает «отклик отправлен» над
    письмом, которого HR не получал.
    """
    assert settings().send_locked is False


def test_sending_locks_once_explicitly_asked():
    """Записанное «true» включает симуляцию — в этом смысл настройки."""
    assert settings(send_locked="true").send_locked is True


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
        ("scoring_threshold", 5),
        ("poll_interval_sec", 1800),
        ("backfill_limit", 15),
        ("dm_backfill_limit", 50),
    ],
)
@pytest.mark.parametrize("raw", ["не число", "1 800"])
def test_a_garbled_whole_number_setting_falls_back_to_its_default(key, default, raw):
    """Мусор в целочисленной настройке откатывается к умолчанию.

    Значения правят руками через DBeaver, и опечатка вроде «1 800» роняла
    приложение на старте — при том, что соседний порог дедупа такое
    переживает откатом.
    """
    assert getattr(settings(**{key: raw}), key) == default


@pytest.mark.parametrize(
    "key", ["poll_interval_sec", "backfill_limit", "dm_backfill_limit"]
)
def test_a_whole_number_setting_right_on_its_bound_is_accepted(key):
    """Значение, равное нижней границе, принимается, а не откатывается.

    Граница названа наименьшим годным, а не первым негодным: единица —
    это «опрашивать раз в секунду» и «брать по одному сообщению», оба
    осмысленны. Откат отсюда молча вернул бы получасовой интервал там,
    где человек просил секунду.
    """
    assert getattr(settings(**{key: "1"}), key) == 1


@pytest.mark.parametrize(
    ("key", "raw", "default"),
    [
        ("poll_interval_sec", "0", 1800),
        ("poll_interval_sec", "-30", 1800),
        ("backfill_limit", "0", 15),
        ("dm_backfill_limit", "0", 50),
    ],
)
def test_a_whole_number_setting_outside_its_range_falls_back(key, raw, default):
    """Число вне допустимого откатывается к умолчанию наравне с мусором.

    Нулевой предел выборки у Telegram означает «вся история», нулевой
    интервал опроса крутит цикл встык, а отрицательный порог оценки пускает
    в новые то, что оценка отбраковала. Числом такое значение быть может,
    годным — нет.
    """
    assert getattr(settings(**{key: raw}), key) == default


@pytest.mark.parametrize("raw", ["0", "-5"])
def test_a_scoring_threshold_below_zero_is_taken_as_given(raw):
    """Порог оценки берётся любым целым, в том числе отрицательным.

    Сам счёт бывает отрицательным — за каждый незнакомый обязательный
    навык снимается балл, — и «пропускать всё» выражается именно порогом
    ниже нуля. Границы снизу у него поэтому нет, в отличие от пределов
    выборки, где ноль означает у Telegram «вся история».
    """
    assert settings(scoring_threshold=raw).scoring_threshold == int(raw)


def test_the_path_to_the_resume_is_empty_until_set():
    """Путь к резюме пуст, пока его не задали."""
    assert settings().cv_path == ""


def test_a_stored_resume_path_is_used():
    """Заданный путь к резюме берётся из настроек."""
    assert settings(cv_path="/tmp/cv.pdf").cv_path == "/tmp/cv.pdf"

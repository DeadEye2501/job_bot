"""Следствия сборки среза профиля для проверки вакансии на пригодность.

Модель-проверяльщик получает не строку профиля из базы, а отдельный срез —
ровно те поля, по которым она решает, подходит ли вакансия. Незаполненный
профиль даёт пустой срез, и проверяльщик читает его как «ограничений нет»:
отказывать всем, пока пользователь не заполнил анкету, значило бы сделать
приложение бесполезным до первой настройки.

Списки копируются, а не передаются как есть: срез уезжает в кэш конвейера и
живёт там до следующей перезагрузки, а строка из базы к тому времени уже
отвязана от сессии.
"""

from backend.llm.candidate import build_candidate_profile
from backend.llm.candidate import CandidateProfile
from backend.models import ProfileLanguage
from tests.factories import profile_row


def test_a_missing_profile_yields_an_empty_slice():
    """Незаполненный профиль даёт пустой срез, а не отказ.

    Проверяльщик читает пустоту как «ограничений нет»; иначе приложение
    отбрасывало бы все вакансии до того, как пользователь заполнит анкету.
    """
    assert build_candidate_profile(None, []) == CandidateProfile()


def test_the_slice_carries_what_the_validator_reads():
    """В срез попадают поля, по которым проверяльщик выносит решение."""
    profile = profile_row(
        title="Python-разработчик",
        location="Ереван",
        grades=["middle", "senior"],
        work_format=["remote"],
        free_preferences="без релокации",
    )

    got = build_candidate_profile(profile, [])

    assert got.title == "Python-разработчик"
    assert got.location == "Ереван"
    assert got.grades == ["middle", "senior"]
    assert got.work_formats == ["remote"]
    assert got.free_preferences == "без релокации"


def test_languages_come_with_their_levels():
    """Языки переносятся вместе с уровнями.

    Уровень здесь решает исход: вакансия с английским B2 подходит или нет
    в зависимости именно от него.
    """
    languages = [
        ProfileLanguage(profile_id=1, language="Русский", level="native"),
        ProfileLanguage(profile_id=1, language="Английский", level="B1"),
    ]

    got = build_candidate_profile(profile_row(), languages)

    assert [(item.name, item.level) for item in got.languages] == [
        ("Русский", "native"),
        ("Английский", "B1"),
    ]


def test_empty_lists_stay_empty_rather_than_absent():
    """Незаполненные списки остаются списками, а не отсутствием.

    У колонок этих полей умолчание — отсутствие, а проверяльщик перебирает
    их циклом: отсутствие уронило бы его на первом же профиле без грейдов.
    """
    profile = profile_row(grades=None, work_format=None)

    got = build_candidate_profile(profile, [])

    assert got.grades == []
    assert got.work_formats == []


def test_the_slice_does_not_share_its_lists_with_the_profile():
    """Срез не делит списки со строкой профиля.

    Он уезжает в кэш конвейера и живёт там до перезагрузки настроек;
    общий список означал бы, что правка анкеты меняет уже сделанный срез
    задним числом.
    """
    profile = profile_row(grades=["middle"], work_format=["remote"])

    got = build_candidate_profile(profile, [])
    profile.grades.append("senior")
    profile.work_format.append("office")

    assert got.grades == ["middle"]
    assert got.work_formats == ["remote"]

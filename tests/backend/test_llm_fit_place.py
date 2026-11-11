"""Следствия зова о месте: что из анкеты доходит до вопроса модели.

Зов решает, может ли кандидат работать там, где требует вакансия, — по месту,
где он живёт, и по гражданству; из предпочтений ему нужны только сведения —
узнать, разрешён ли переезд. Сами правила держит наставление; здесь — что
модель получает то, по чему их применять.
"""

from functools import partial

from backend.llm.candidate import CandidateProfile
from backend.llm.fit_place import validate_place_fit
from backend.llm.fit_preferences import validate_preferences_fit
from tests.backend.fixtures.fit import verdict
from tests.fakes.llm import CHAT, fit_answer, messages_of, provider

_check = partial(verdict, validate_place_fit)


async def _system_for(profile: CandidateProfile) -> str:
    client = provider({CHAT: fit_answer("fit", "место подходит")})
    await _check(client, profile=profile)
    return messages_of(client.sent[0])["system"]


async def test_where_the_candidate_lives_and_the_citizenship_reach_the_question():
    system = await _system_for(CandidateProfile(location="Город Q7", citizenship="Страна Q9"))

    assert "Город Q7" in system and "Страна Q9" in system


async def test_where_the_candidate_lives_goes_to_this_question_alone():
    """Место — критерий одного зова: в зове предпочтений его нет, иначе о нём
    судили бы двое и разошлись бы."""
    client = provider({CHAT: fit_answer("fit", "блокеров нет")})

    await verdict(validate_preferences_fit, client,
                  profile=CandidateProfile(location="Город Q7", bans=["без крипты"]))

    assert "Город Q7" not in messages_of(client.sent[0])["system"]


async def test_the_info_reaches_the_question_for_the_word_on_relocation_one_line_each():
    """Строка на сведение: слитые через пробел, они читались бы одной фразой."""
    system = await _system_for(CandidateProfile(info=["есть права", "переезд в страну Q5 возможен"]))

    assert "\n  - есть права\n  - переезд в страну Q5 возможен" in system


async def test_no_info_is_named_absent():
    system = await _system_for(CandidateProfile())

    assert "куда кандидат готов переехать): —" in system


async def test_bans_do_not_reach_the_question_on_place():
    """Запрет о присутствии судит зов запретов: увидев его здесь, зов места
    отказывал бы и по нему, и о нём судили бы двое."""
    system = await _system_for(CandidateProfile(bans=["не готов бывать в стране Q5"]))

    assert "не готов бывать в стране Q5" not in system


async def test_each_ban_reaches_the_question_on_bans():
    client = provider({CHAT: fit_answer("fit", "блокеров нет")})

    await verdict(validate_preferences_fit, client,
                  profile=CandidateProfile(bans=["без крипты", "без гемблинга"], info=["есть права"]))

    system = messages_of(client.sent[0])["system"]
    assert "- без крипты\n- без гемблинга" in system
    assert "есть права" not in system

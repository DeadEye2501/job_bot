"""Следствия зова о месте: что из анкеты доходит до вопроса модели.

Зов решает, может ли кандидат работать там, где требует вакансия, — по месту,
где он живёт, и по гражданству; предпочтения ему нужны только затем, чтобы
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
                  profile=CandidateProfile(location="Город Q7", free_preferences="без крипты"))

    assert "Город Q7" not in messages_of(client.sent[0])["system"]


async def test_the_preferences_reach_the_question_for_the_word_on_relocation():
    system = await _system_for(CandidateProfile(free_preferences="переезд в страну Q5 возможен"))

    assert "переезд в страну Q5 возможен" in system

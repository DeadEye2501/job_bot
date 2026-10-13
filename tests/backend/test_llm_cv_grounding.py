"""Следствия сверки разобранного резюме с его же текстом.

Модель на запрет «не выдумывай» полагаться не даёт: маленькая её не держит.
Отсюда проверка кодом — по тем полям, где выдумка меняет отбор вакансий.
"""

from backend.llm.cv_grounding import grounded_in_cv
from backend.payloads import ParsedCvLanguage
from tests.factories_cv import parsed_cv, parsed_cv_place, parsed_cv_profile, parsed_cv_skill


def test_a_language_the_resume_never_names_is_dropped():
    """Резюме маркетолога языков не называет, а модель дописала французский."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Французский", level="B2")]
    )

    grounded = grounded_in_cv(parsed, "Маркетолог. Яндекс.Директ, Google Ads, CRM.")

    assert grounded.languages == []


def test_a_language_the_resume_names_survives():
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    grounded = grounded_in_cv(parsed, "Иностранные языки: Английский — B2")

    assert [lang.language for lang in grounded.languages] == ["Английский"]


def test_a_language_named_in_a_declined_form_survives():
    """«Владею английским» — тот же язык, лишь в другом падеже."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    grounded = grounded_in_cv(parsed, "Свободно владею английским, читаю документацию.")

    assert [lang.language for lang in grounded.languages] == ["Английский"]


def test_a_grade_the_resume_never_names_is_dropped():
    """У электрика в резюме нет ни слова о грейде, а модель выдала два."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["middle", "senior"]))

    grounded = grounded_in_cv(parsed, "Электрик. Опыт работы 8 лет. Группа допуска 4.")

    assert grounded.profile.grades == []


def test_a_grade_the_resume_names_survives():
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["senior"]))

    grounded = grounded_in_cv(parsed, "Senior Python Developer, ищу удалённую работу.")

    assert grounded.profile.grades == ["senior"]


def test_a_grade_named_in_russian_survives():
    """Своё звание пишут и по-русски, и терять его из-за этого незачем."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["lead"]))

    grounded = grounded_in_cv(parsed, "Ищу позицию тимлида в продуктовой команде.")

    assert grounded.profile.grades == ["lead"]


def test_the_rest_of_the_resume_is_left_alone():
    """Сверка касается двух полей; навыки, опыт и прочий профиль не её дело."""
    parsed = parsed_cv(
        profile=parsed_cv_profile(location="Тверь", education="Политех"),
        skills=[parsed_cv_skill("Python")],
        experience=[parsed_cv_place(company="Контур")],
    )

    grounded = grounded_in_cv(parsed, "Резюме без единого слова про грейды и языки.")

    assert [skill.name for skill in grounded.skills] == ["Python"]
    assert [place.company for place in grounded.experience] == ["Контур"]
    assert grounded.profile.location == "Тверь"
    assert grounded.profile.education == "Политех"


def test_a_language_whose_name_is_too_short_to_check_survives():
    """«中文» проверить нечем: корня у такого имени не бывает.

    Непроверяемое остаётся. Сверка заведена против выдумки, а выбросить
    настоящее — беда крупнее той, от которой она сторожит.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="中文", level="B1")])

    grounded = grounded_in_cv(parsed, "Резюме на русском языке без слова «китайский».")

    assert [lang.language for lang in grounded.languages] == ["中文"]


def test_a_grade_is_not_confirmed_by_a_word_it_merely_hides_inside():
    """«middleware» — не грейд, «валидация» — не лид.

    Ищи сверка подстрокой без границ слова, и выдуманный грейд подтверждался
    бы любым словом, внутри которого он случайно оказался.
    """
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["middle", "lead"]))

    grounded = grounded_in_cv(
        parsed, "Писал middleware, занимался валидацией и консолидацией отчётов."
    )

    assert grounded.profile.grades == []


def test_a_grade_named_with_a_russian_ending_survives():
    """Звание в тексте склоняют: «сеньора», «джуна», «тимлида»."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["senior"]))

    grounded = grounded_in_cv(parsed, "Ищу работу сеньора в продуктовой команде.")

    assert grounded.profile.grades == ["senior"]


def test_a_grade_named_as_an_intern_survives():
    """«Стажёр» — то же звание, что junior, и терять его незачем."""
    parsed = parsed_cv(profile=parsed_cv_profile(grades=["junior"]))

    grounded = grounded_in_cv(parsed, "Стажёр отдела аналитики, ищу первую работу.")

    assert grounded.profile.grades == ["junior"]


def test_an_invented_native_language_is_dropped_like_any_other():
    """Родному языку поблажки нет, и это главное здесь.

    Модель выводит родной язык из фамилии кандидата. Освободи его от сверки —
    и выдуманный «Армянский» пройдёт в анкету, а настоящий язык резюме уже не
    добавится: родной ведь формально есть. Дыра открывается ровно там, ради
    чего сверка заведена.
    """
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Армянский", level="native")]
    )

    grounded = grounded_in_cv(parsed, "Саркисян Ашот. Электрик. Опыт 8 лет.")

    assert grounded.languages == []


def test_a_language_level_the_text_never_names_falls_back_to_the_highest():
    """Уровень тоже сверяется с текстом, а не только сам язык.

    «Английский (технический)» модель превращает в B1 или B2 — по настроению.
    Ни того, ни другого в резюме нет. Взамен ставится высший: уровня человек
    не назвал, а не называют его те, кто в языке уверен. Нижний на его месте
    отрезал бы такому человеку все вакансии, где язык нужен.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B1")])

    grounded = grounded_in_cv(parsed, "Иностранные языки: английский (технический)")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C2")
    ]


def test_a_language_level_named_in_the_text_survives():
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="C1")])

    grounded = grounded_in_cv(parsed, "Иностранные языки: английский — C1")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C1")
    ]


def test_a_native_level_is_not_asked_to_be_named_in_the_text():
    """Родной уровень выводится из языка письма, в тексте его слова нет."""
    parsed = parsed_cv(
        languages=[ParsedCvLanguage(language="Английский", level="native")]
    )

    grounded = grounded_in_cv(parsed, "Иностранные языки: английский")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "native")
    ]


def test_a_level_hidden_inside_another_word_does_not_confirm_it():
    """«B2B-продажи» — не уровень английского B2."""
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B2")])

    grounded = grounded_in_cv(parsed, "Английский. Опыт B2B-продаж и работы с CRM.")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C2")
    ]


def test_a_level_typed_in_cyrillic_letters_is_still_its_own():
    """«А1» русской буквой — тот же A1, и повышать его до высшего нельзя.

    Обозначения шкалы набирают в русской раскладке сплошь и рядом: А, В, С в
    ней неотличимы на вид от латинских. Не узнай сверка своё же обозначение —
    и честно названный начальный уровень стал бы высшим.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="A1")])

    grounded = grounded_in_cv(parsed, "Иностранные языки\nАнглийский - А1")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "A1")
    ]


def test_a_level_word_from_another_sentence_does_not_confirm_it():
    """«Свободный график» — не свободный английский.

    Слова уровней живут в резюме своей жизнью: «свободный график»,
    «продвинутый пользователь Excel», «базовое понимание процессов». Ищи их по
    всему тексту — и любой выдуманный уровень найдёт себе подтверждение.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="C1")])
    text = (
        "Ищу удалённую работу, свободный график.\n"
        "Продвинутый пользователь Excel.\n\n"
        "Иностранные языки\nАнглийский\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C2")
    ]


def test_a_level_word_belongs_to_the_language_it_stands_next_to():
    """Два языка подряд: слово соседа своему уровню не засчитывается."""
    parsed = parsed_cv(
        languages=[
            ParsedCvLanguage(language="Английский", level="C1"),
            ParsedCvLanguage(language="Немецкий", level="A1"),
        ]
    )
    text = "Иностранные языки\nАнглийский — свободно\nНемецкий — базовый\n"

    grounded = grounded_in_cv(parsed, text)

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C1"),
        ("Немецкий", "A1"),
    ]


def test_a_longer_level_name_is_not_confirmed_by_its_own_tail():
    """«Upper-Intermediate» — не «Intermediate», и B1 отсюда не следует.

    Взамен неподтверждённого читается написанное рядом с языком, а написано
    там B2. Совпади короткое имя с длинным — и B1 остался бы как есть.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B1")])

    grounded = grounded_in_cv(parsed, "Языки: Английский — Upper-Intermediate")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "B2")
    ]


def test_a_work_format_the_resume_never_names_is_dropped():
    """«Полный день, 5/2» — не про офис, удалёнку или гибрид.

    Формат работы модель выводит из графика и из готовности к переезду, а по
    нему отбирают вакансии наравне с грейдом: приписанный офис отрежет
    человеку всю удалённую работу.
    """
    parsed = parsed_cv(profile=parsed_cv_profile(work_format=["office"]))
    text = "График: полный день, 5/2\nГотовность к переезду: нет"

    grounded = grounded_in_cv(parsed, text)

    assert grounded.profile.work_format == []


def test_a_work_format_the_resume_names_survives():
    """Названный формат остаётся, в каком бы виде его ни написали."""
    parsed = parsed_cv(
        profile=parsed_cv_profile(work_format=["remote", "hybrid", "office"])
    )
    text = "Режим работы: гибрид или удалённо, готова выходить в офис раз в неделю"

    grounded = grounded_in_cv(parsed, text)

    assert grounded.profile.work_format == ["remote", "hybrid", "office"]


def test_ms_office_in_the_skills_does_not_confirm_the_office_format():
    """«MS Office» — программа, а не работа из офиса.

    Английское «office» само по себе форматом не считается именно поэтому: оно
    сидит в названии самой ходовой программы, какая только бывает в резюме.
    """
    parsed = parsed_cv(profile=parsed_cv_profile(work_format=["office"]))
    text = "Профессиональные навыки\n- MS Office, 1С\nГрафик: полный день, 5/2"

    grounded = grounded_in_cv(parsed, text)

    assert grounded.profile.work_format == []


def test_one_unnamed_format_takes_the_whole_list_with_it():
    """Формат сверяется списком целиком, а не по одному значению.

    Пустой список форматов выключает отбор вакансий по формату, непустой —
    включает и отвергает всё, чего в нём нет. Значит вредна не потеря
    значения, а неверный непустой список: оставь «гибрид» от пары
    «гибрид, офис» — и человеку начнут отказывать по офисным вакансиям,
    которых он не отвергал.

    Грейд сверяется иначе, по одному значению, и это не разнобой: звания
    («senior», «тимлид») в резюме ни с чем не путаются, а слова форматов —
    «офис», «удалён» — сидят внутри «офисного пакета» и «удаления данных».
    """
    parsed = parsed_cv(profile=parsed_cv_profile(work_format=["hybrid", "office"]))

    grounded = grounded_in_cv(parsed, "Режим работы: гибрид, два дня дома")

    assert grounded.profile.work_format == []


def test_a_level_word_of_the_next_language_stays_with_it():
    """Окно уровня кончается там, где начинается следующий язык.

    Заявленный уровень английского в тексте не назван, и подтвердить его
    нечем — но строкой ниже стоит «базовый» немецкого. Дотянись окно до него,
    и английский получил бы A1 чужим словом.
    """
    parsed = parsed_cv(
        languages=[
            ParsedCvLanguage(language="Английский", level="A1"),
            ParsedCvLanguage(language="Немецкий", level="A1"),
        ]
    )
    text = "Иностранные языки\nАнглийский\nНемецкий — базовый\n"

    grounded = grounded_in_cv(parsed, text)

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "C2"),
        ("Немецкий", "A1"),
    ]


def test_a_language_mentioned_in_prose_does_not_steal_its_own_window():
    """«Пять лет в англоязычной команде» — не то место, где назван уровень.

    Корень языка ловится и в таком слове, а раздел с настоящим уровнем стоит
    ниже. Возьми первое вхождение — и честный B1 подменится высшим: сверка
    выбросит правду, чего ей делать нельзя.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="B1")])
    text = (
        "О себе\nПять лет в англоязычной команде, ежедневные созвоны.\n\n"
        "Иностранные языки\nАнглийский — B1\n"
    )

    grounded = grounded_in_cv(parsed, text)

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "B1")
    ]


def test_the_level_written_beside_the_language_wins_over_the_claimed_one():
    """Модель перевела «начальный» в «Elementary» — уровень берут из резюме.

    Заявленный A2 текстом не подтверждается: слова «elementary» в русском
    резюме нет. Но рядом с языком написано «начальный», и это A1 — читать надо
    его, а не уходить в запасной высший.
    """
    parsed = parsed_cv(languages=[ParsedCvLanguage(language="Английский", level="A2")])

    grounded = grounded_in_cv(parsed, "Иностранные языки\nАнглийский язык — начальный")

    assert [(x.language, x.level) for x in grounded.languages] == [
        ("Английский", "A1")
    ]

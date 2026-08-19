"""Отбор списка вакансий, прочитанный из нагрузки окна.

Четырнадцать полей одного экрана — то, что человек выбрал в фильтрах.
Отдельным модулем, а не в слоте, по тому же доводу, по какому заведён
`client/form_payloads.py`: слот держит сигналы и сессию, а не разбор нагрузки,
и полсотни строк чтения до первого обращения к репозиторию прятали собой всё
остальное, что слот делает.

От соседей отличается предметом. `page.py` читает страницу — она одна у
четырёх экранов; здесь отбор, и он только у вакансий. `form_payloads.py` (он
пакетом выше) читает поля новой записи, то есть то, что окно **пишет**, а не
то, чем оно просит выбрать.
"""

from __future__ import annotations

from backend.payloads import VacancyFilter
from backend.incoming import float_or_none, int_or_none, moment_or_none, str_list, text_or_none
from client.bridge.page import Page


def read_vacancy_filter(payload: dict, page: Page) -> VacancyFilter:
    """Отбор из нагрузки окна; страница приходит доводом, уже прочитанной.

    Страница отдельно потому, что она общая четырём экранам и читается своим
    объявлением вместе с потолком и режимом. Складывать её обратно в отбор
    приходится оттого, что список и страница уезжают в репозиторий одним
    предметом.

    Пустой список выбранного значит «не отбирали», а не «отобрали пустым»:
    различать эти два случая умеет только зовущий, репозиторию же пустой
    список отсёк бы всё.

    Умолчание порядка берётся у самого отбора: написанное здесь вторым словом
    разошлось бы с объявленным молча, а видно это стало бы одной строкой в
    списке, вставшей не туда.
    """
    return VacancyFilter(
        sort=text_or_none(payload.get("sort")) or VacancyFilter.sort,
        search=text_or_none(payload.get("search")),
        statuses=str_list(payload.get("statuses")) or None,
        channels=str_list(payload.get("channels")) or None,
        companies=str_list(payload.get("companies")) or None,
        score_min=int_or_none(payload.get("score_min")),
        score_max=int_or_none(payload.get("score_max")),
        salary_min=float_or_none(payload.get("salary_min")),
        salary_max=float_or_none(payload.get("salary_max")),
        grade=text_or_none(payload.get("grade")),
        remote=text_or_none(payload.get("remote")),
        hr_contact=text_or_none(payload.get("hr_contact")),
        date_from=moment_or_none(payload.get("date_from")),
        date_to=moment_or_none(payload.get("date_to")),
        limit=page.limit,
        offset=page.offset,
    )

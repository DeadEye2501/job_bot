"""Отметка последней жизни вакансии — из чего складывается и как её спросить.

Своим модулем, потому что спрашивают её двое и по-разному: список сортирует по
ней прямо в запросе, а окно берёт её готовой для показанных строк. Написанные
порознь, перечни источников разъезжались бы молча — вакансия стояла бы первой,
показывая дату второй.

Отсюда же берут свои отметки и соседи по вопросу «жива ли вакансия»: срок
молчания (`vacancies_ghosting`) и разбивка статусов на экране статистики.
Метки у них другие — последнее письмо собеседника, вход в нынешний статус, —
но объявлены они здесь же и одним местом на всех.
"""

from sqlalchemy import case, func, select

from backend.models import Message, Vacancy, VacancyEvent, VacancyStatusHistory


def _greatest_pair(a, b):
    # NULL-safe row-wise greatest: SQLite has no GREATEST(), and
    # NULL > anything is NULL, so we have to spell it out.
    return case((a.is_(None), b), (b.is_(None), a), (a > b, a), else_=b)


def _greatest(*cols):
    out = cols[0]
    for c in cols[1:]:
        out = _greatest_pair(out, c)
    return out


def last_incoming_subq(ids: list[int] | None = None):
    """Когда по каждой вакансии последний раз писал собеседник.

    Одно объявление на два счёта: метку активности для списка считают здесь,
    срок молчания — в `vacancies_ghosting`, и оба спрашивают ровно это.
    Написанные порознь, они разошлись бы молча — вакансия ушла бы в тишину,
    показывая свежую дату.

    Письмо берётся только входящее: ждём мы ответа собеседника, а не себя, и
    своё письмо двигало бы обе метки вперёд, пока разговор стоит.
    """
    q = select(
        Message.vacancy_id.label("vid"),
        func.max(Message.sent_at).label("max_at"),
    ).where(Message.is_incoming.is_(True))
    if ids is not None:
        q = q.where(Message.vacancy_id.in_(ids))
    return q.group_by(Message.vacancy_id).subquery("msg_agg")


def entered_current_status_at():
    """Когда вакансия встала туда, где стоит сейчас.

    Последний переход **в нынешний статус**, а нет истории — заведение
    строки: в «новую» вакансия попадает самим появлением, и перехода туда
    никто не пишет.

    Берётся **последний** такой переход: вакансия могла побывать в этом
    статусе, откатиться и вернуться, и свежесть ей даёт возвращение.

    С шапкой экрана статистики счёт сходится не буква в букву: там считают
    первый переход в статус, а тут последний в нынешний. Расходятся они
    только на вернувшейся вакансии, а сходятся в главном — окно у обоих
    меряется переходом. Считай разбивка по дате появления — вакансия,
    заведённая в позапрошлом месяце и откликнутая вчера, попадала бы в
    «+1 за неделю» наверху и не попадала бы в столбик под ним.

    Второй потребитель — срок молчания: для него это «когда вакансия встала
    туда, где стоит» и есть один из признаков жизни.
    """
    last_into_current = (
        select(func.max(VacancyStatusHistory.changed_at))
        .where(
            VacancyStatusHistory.vacancy_id == Vacancy.id,
            VacancyStatusHistory.status == Vacancy.status,
            # Только настоящий переход. Строку истории заводит и комментарий к
            # нынешнему статусу — у неё тот же статус и свежее время, но
            # вакансия никуда не двигалась. Считай мы её — дописанная вчера
            # заметка к майскому оферу показывала бы офер сегодняшним.
            VacancyStatusHistory.applied.is_(True),
        )
        .scalar_subquery()
    )
    return func.coalesce(last_into_current, Vacancy.created_at)

def activity_aggs(ids: list[int] | None = None) -> tuple:
    """Свежайшие событие, смена статуса и письмо HR — по строке на вакансию.

    Названные номера сужают все группировки: спрашивая метку для полусотни
    показанных строк, незачем группировать всю ленту событий. Список так
    сузить нельзя — он отбирает уже после соединения, — поэтому довод
    необязательный.
    """
    event_q = select(
        VacancyEvent.vacancy_id.label("vid"),
        func.max(VacancyEvent.created_at).label("max_at"),
    )
    status_q = select(
        VacancyStatusHistory.vacancy_id.label("vid"),
        func.max(VacancyStatusHistory.changed_at).label("max_at"),
    )
    if ids is not None:
        event_q = event_q.where(VacancyEvent.vacancy_id.in_(ids))
        status_q = status_q.where(VacancyStatusHistory.vacancy_id.in_(ids))
    return (
        event_q.group_by(VacancyEvent.vacancy_id).subquery("event_agg"),
        status_q.group_by(VacancyStatusHistory.vacancy_id).subquery("status_agg"),
        last_incoming_subq(ids),
    )


def activity_ts(aggs: tuple):
    """Метка активности вакансии — позднейшее из пяти времён."""
    return _greatest(
        Vacancy.created_at,
        Vacancy.posted_at,
        *[agg.c.max_at for agg in aggs],
    )


def join_activity(stmt, aggs: tuple):
    """Прицепить к запросу всё, из чего считается метка.

    Стыки идут вместе с самим выражением: забудь один — и база ответит
    ошибкой не про метку, а про неизвестную таблицу.
    """
    for agg in aggs:
        stmt = stmt.outerjoin(agg, agg.c.vid == Vacancy.id)
    return stmt

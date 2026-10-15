"""Разбор объявления о вакансии в структурированные поля."""

import logging
import re
from dataclasses import replace

import httpx

from adapters.lm_chat import ChatRequest, chat
from backend.domain.company_names import capitalized_company_name
from backend.domain.contact_keys import EMAIL_PATTERN, PHONE_PATTERN
from backend.domain.taxonomy import GRADES, WORK_FORMATS
from backend.domain.telegram_identity import normalize_username
from backend.payloads import ParsedVacancy

from backend.incoming import normalize_enum, str_list
from backend.llm.answers import json_object, read_with_a_second_try, str_or_none
from backend.llm.candidate import CandidateProfile, format_known_skills
from backend.llm.rules import AGGREGATOR_HOSTS_LINE, VACANCY_TEXT_CHARS, in_user_language
from backend.llm.external import external_block
from backend.llm.skills import clean_stack_items
from backend.llm.vacancy_prompt import PARSE_VACANCY_PROMPT

logger = logging.getLogger(__name__)

# Потолок токенов на разбор объявления и запас на второй заход. Первый заход
# идёт обычным потолком: платить за запас на каждом посте незачем, длинных
# среди них меньшинство. Оборвавшийся ответ переспрашивается с запасом — см.
# `answers.wants_more_room`, — и если не хватило и его, разбор сдаётся, а
# зовущий записывает строку с названной причиной вместо вечного перебора.
MAX_PARSE_TOKENS = 1200
ROOMIER_PARSE_TOKENS = 2400


# Sanitiser для company_name: иногда LLM прилепляет URL прямо в название
# («КА https://example.com/», «Brand foo.com»). Регексп ловит trailing
# URL/домен и вырезает; в `parsed_vacancy_from_json` вырезанный URL уезжает в
# company_website если оно пусто.
_DOMAIN = r"(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"
_TRAILING_URL_RE = re.compile(rf"\s*(https?://[^\s)]+|{_DOMAIN}(?:/[^\s)]*)?)\)?\s*$")


# Чистка other_contacts: пост часто кончается ссылкой-словом
# («Откликнуться», «Подробнее»), и способ отклика приезжает подписью. Адрес к
# ней подставляет чтение поста (`extract_post_text`), но подставить
# нечего, когда ссылки нет вовсе, — а «пишите в комментарии» модель приносит
# как контакт и без неё. Такая подпись легла бы контактом вакансии
# «Откликнуться»: контакт вроде бы есть, а откликаться по нему некуда.
# Настоящий способ отклика узнаётся по адресу внутри строки — почте, ссылке,
# домену, телефону.
_CONTACT_ADDRESS_RE = re.compile(
    rf"""
      {EMAIL_PATTERN}                                   # почта
    | https?://\S+                                      # ссылка целиком
    | {_DOMAIN}(?:/\S*)?                                # домен
    | {PHONE_PATTERN}                                   # телефон
    """,
    re.VERBOSE,
)

# Адрес, дописанный за подписью ссылки при чтении поста (`extract_post_text`).
# Модель приносит их вместе — «контакты в описании (https://acme.com/jobs)», — а
# в контакт вакансии нужен способ отклика, а не пересказ поста.
_LABELLED_ADDRESS_RE = re.compile(r"\(([^()\s]+)\)\s*$")


# Hard cap на длину description'а — защита от LLM, который проигнорирует
# «3-6 предложений» и выдаст 2KB-блок. UI всё равно режет в трёх строках
# до раскрытия, но в БД лучше не складывать гигабайты.
_DESCRIPTION_MAX_CHARS = 1500


def _split_stack(data: dict) -> tuple[list, list]:
    """Стек вакансии двумя списками: обязательное и желательное.

    Stack is split into two lists (``stack_required`` / ``stack_preferred``).
    Legacy fallback: if LLM still emits the old single ``stack`` field
    (e.g. older model snapshot ignored prompt update), treat it all as
    required — this is the safe default (penalises unmatched as -1, no
    silent +0 from misclassifying everything as preferred).

    Набор виденного один на оба списка: технология, попавшая в оба, должна
    остаться в обязательном и не задваиваться в желательном.
    """
    seen: set[str] = set()
    if "stack_required" in data or "stack_preferred" in data:
        return (
            clean_stack_items(data.get("stack_required"), seen),
            clean_stack_items(data.get("stack_preferred"), seen),
        )
    return clean_stack_items(data.get("stack"), seen), []


def _company_name_and_site(
    company_name: str | None, company_website: str | None
) -> tuple[str | None, str | None]:
    """Разнять имя компании и прилипшую к нему ссылку.

    URL pollution: если LLM прилепил URL к company_name, вырезаем его из
    имени и (если company_website пуст) кладём туда. Заодно это делает
    сведение по имени рабочим — без хвоста «КА https://example.com/»
    сходится с уже заведённой «КА». Имя, состоящее из одной ссылки, не
    трогаем: пустое имя хуже грязного.

    Скобки вокруг адреса снимаются здесь же. Пару «имя (адрес)» собирает
    чтение поста, подставляя адрес спрятанной ссылки за её подписью, и без
    этого в имени оставалась бы открывающая скобка — а по ней сведение
    компаний уже не сходится, — и закрывающая уезжала бы внутрь адреса,
    ломая переход на сайт.
    """
    if not company_name:
        return company_name, company_website
    m = _TRAILING_URL_RE.search(company_name)
    if not m:
        return company_name, company_website
    cleaned_name = company_name[: m.start()].rstrip(" -–—|,;:(")
    if not cleaned_name:
        return company_name, company_website
    if company_website:
        return cleaned_name, company_website
    return cleaned_name, m.group(1).strip()


def _address_after_label(value: str) -> str:
    """Оставить один адрес от пары «подпись (адрес)»; иначе отдать как было.

    Пару собирает чтение поста (`extract_post_text`), подставляя адрес
    спрятанной ссылки за её подписью, и модель приносит её целиком. Записанная
    как есть, она не адрес, а пересказ: по «Анне (https://t.me/anna_hr)» ни
    ника не разобрать, ни по контакту вакансии не откликнуться.

    Адрес внутри обычной фразы это не задевает: скобок там нет, и фраза
    остаётся дословной.
    """
    labelled = _LABELLED_ADDRESS_RE.search(value)
    if labelled and _CONTACT_ADDRESS_RE.fullmatch(labelled.group(1)):
        return labelled.group(1)
    return value


def _contacts(
    hr_contact: str | None, other_contacts: list[str]
) -> tuple[str | None, list[str]]:
    """Контакты, разложенные по своим полям: ник собеседника и все прочие.

    Поля модель путает. Из строки «Контакты: почта / Telegram @ник» она
    приносит почту полем собеседника, а ник теряет вовсе. Поле собеседника
    читает `normalize_username`, и почта в нём неразрешима — записанная туда,
    она пропадает с глаз совсем: карточка этого поля не показывает, она
    показывает способы отклика. Не-ник поэтому переносится к ним — последним,
    за названными моделью в отведённом им поле.
    """
    hr_contact = _address_after_label(hr_contact) if hr_contact else None
    if hr_contact and normalize_username(hr_contact) is None:
        other_contacts = [*other_contacts, hr_contact]
        hr_contact = None
    return hr_contact, [way for way in map(_way_to_apply, other_contacts) if way]


def _way_to_apply(other_contact: str) -> str | None:
    """Оставить способ отклика, только если в нём есть адрес.

    Строка без почты, ссылки, домена или телефона — не контакт, а подпись
    кнопки («Откликнуться») или указание словами («пишите в комментарии»).
    Пустоты она не заменяет: карточка показывает её как контакт, и человек
    идёт по ней в никуда.

    От подписи со своим адресом в скобках остаётся один адрес. Такую пару
    собирает чтение поста, подставляя адрес спрятанной ссылки за её подписью;
    модель приносит её целиком, и записанная как есть, она читалась бы в
    контактах не адресом, а пересказом. Адрес внутри обычной фразы («резюме на
    careers.acme.com/apply») это не задевает: скобок там нет, и фраза остаётся
    дословной.
    """
    other_contact = _address_after_label(other_contact)
    if _CONTACT_ADDRESS_RE.search(other_contact):
        return other_contact
    logger.debug("parse_vacancy: способ отклика без адреса отброшен: %r", other_contact)
    return None


def parsed_vacancy_from_json(answer: str) -> ParsedVacancy | None:
    """Ответ модели, прочитанный в свёртку разобранного объявления.

    Имя открытое: читают этим не только разбор поста. Тем же чтением приходит
    к записи и объявление, найденное вне Telegram, — приведение грейда и
    формата к перечням, чистка стека, разбор контактов и обрезка описания
    обязаны быть у обоих одни.
    """
    data = json_object(answer, logger, "parse_vacancy")
    if data is None:
        return None
    title = str_or_none(data.get("title"))
    if title is None:
        logger.debug("parse_vacancy: empty/missing title in JSON keys=%s", list(data.keys()))
        return None
    return _vacancy_of(data, title)


def _vacancy_of(data: dict, title: str) -> ParsedVacancy:
    """Свёртка из ответа, в котором главное поле уже нашлось.

    Отдельно от чтения ответа: там решают, есть ли что собирать вообще, здесь
    собирают — поле за полем.
    """

    def _text_field(field: str) -> str | None:
        return str_or_none(data.get(field))

    description = _text_field("description")
    if description and len(description) > _DESCRIPTION_MAX_CHARS:
        description = description[:_DESCRIPTION_MAX_CHARS].rstrip() + "…"
    stack_required, stack_preferred = _split_stack(data)
    company_name, company_website = _company_name_and_site(
        _text_field("company_name"), _text_field("company_website")
    )
    hr_contact, other_contacts = _contacts(
        _text_field("hr_contact"), str_list(data.get("other_contacts"))
    )
    return ParsedVacancy(
        title=title,
        description=description,
        company_name=capitalized_company_name(company_name),
        company_website=company_website,
        hr_contact=hr_contact,
        other_contacts=other_contacts,
        stack_required=stack_required,
        stack_preferred=stack_preferred,
        grade=normalize_enum(data.get("grade"), GRADES),
        salary=_text_field("salary"),
        remote=normalize_enum(data.get("remote"), WORK_FORMATS),
        location=_text_field("location"),
        language=_text_field("language"),
    )


def _parse_request(text: str, profile: CandidateProfile, max_tokens: int) -> ChatRequest:
    """Что спросить у модели: правила разбора и сам пост как данные."""
    system_prompt = in_user_language(PARSE_VACANCY_PROMPT.replace(
        "{KNOWN_SKILLS_BLOCK}", format_known_skills(profile.known_skills)
    ).replace("{AGGREGATOR_HOSTS}", AGGREGATOR_HOSTS_LINE), profile.user_language)
    user_content = external_block(
        text,
        "текст объявления о вакансии",
        "Извлеки факты в JSON по правилам system prompt'а.",
    )
    return ChatRequest(
        purpose="parse_vacancy",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
    )


def _without_the_channel_itself(
    parsed: ParsedVacancy, channel_username: str | None
) -> ParsedVacancy:
    """Убрать из контактов сам канал: он не собеседник и не способ отклика.

    Оба поля разом, потому что приезжает он в оба. Чтение поста дописывает за
    подписью ссылки её адрес, и подпись канала в подвале поста приходит
    моделью как способ отклика. В контактах вакансии он читается контактом,
    а ведёт туда, откуда пост и взят.

    Ник приводится общим правилом, а не своими руками: своими хвост ссылки
    становится ником, и `t.me/канал/1481` даёт «1481».
    """
    if not channel_username:
        return parsed

    def is_the_channel(contact: str | None) -> bool:
        name = normalize_username(contact)
        return name is not None and name.lower() == channel_username.lower()

    return replace(
        parsed,
        hr_contact=None if is_the_channel(parsed.hr_contact) else parsed.hr_contact,
        other_contacts=[
            way for way in parsed.other_contacts if not is_the_channel(way)
        ],
    )


def _log_parsed(parsed: ParsedVacancy) -> None:
    logger.debug(
        "parse_vacancy: title=%r company=%r hr=%s other=%s stack_req=%d stack_pref=%d",
        parsed.title,
        parsed.company_name,
        parsed.hr_contact,
        parsed.other_contacts,
        len(parsed.stack_required or []),
        len(parsed.stack_preferred or []),
    )


async def parse_vacancy(
    text: str,
    client: httpx.AsyncClient,
    model: str,
    channel_username: str | None = None,
    *,
    profile: CandidateProfile,
) -> tuple[ParsedVacancy | None, str | None]:
    """Разбор объявления либо причина, по которой спросить не вышло.

    Причина отделена от пустого разбора нарочно: «модель ответила, а брать в
    посте нечего» — приговор объявлению, «спросить не вышло» — не приговор
    ничему. Что делать с этим различием, решает зовущий; здесь только не
    схлопывается то, что схлопнуть потом уже нельзя.

    Неразбираемый ответ причиной не считается: модель ответила, а сказала
    несуразицу — это по-прежнему пустой разбор. А вот оборванный на пределе
    токенов, из которого объект не собрался, причина: пустой разбор здесь
    прочли бы как «в посте нет вакансии», и строку удалили бы навсегда.
    Разобравшийся при обрыве ответ берут как есть — недостающие поля не беда.
    """
    if not text:
        return None, None
    text = text[:VACANCY_TEXT_CHARS]
    logger.debug("parse_vacancy: %d chars channel=@%s", len(text), channel_username or "?")
    parsed, trouble = await read_with_a_second_try(
        lambda room: chat(
            client, model, _parse_request(text, profile, room), logger
        ),
        parsed_vacancy_from_json,
        (MAX_PARSE_TOKENS, ROOMIER_PARSE_TOKENS),
        (logger, "parse_vacancy"),
        empty_means="модель сочла пост не вакансией",
    )
    if parsed is None:
        return None, trouble
    parsed = _without_the_channel_itself(parsed, channel_username)
    _log_parsed(parsed)
    return parsed, None

"""Разбор ответа HR: на каком этапе теперь отклик."""


import logging
from dataclasses import dataclass

import httpx

from adapters.lm_chat import CUT_BY_LIMIT, ChatRequest, chat

from backend.domain.transitions import ALLOWED_AUTO_TRANSITIONS
from backend.models import VacancyStatus
from backend.payloads import Classification

from backend.llm.answers import ONLY_JSON, json_object, log_unparseable, str_or_none
from backend.llm.external import external_block
from backend.llm.rules import in_user_language

logger = logging.getLogger(__name__)


# Бюджет токенов на вердикт о письме HR. Двухсот не хватало вовсе:
# рассуждающая модель тратит их на размышление до ответа, упирается в предел,
# и вердикта не остаётся — а обрыв здесь означает, что письмо не разобрано
# (см. `MAX_COVER_LETTER_TOKENS`, где счёт тот же).
MAX_CLASSIFY_TOKENS = 1200


CLASSIFY_HR_REPLY_PROMPT_TEMPLATE = """Ты классифицируешь ответ HR-а кандидату по тому, на каком этапе сейчас находится отклик.

ТЕКУЩИЙ СТАТУС ВАКАНСИИ: {CURRENT_STATUS}
ДОПУСТИМЫЕ статусы для ответа (выбирай ТОЛЬКО из этого списка): {ALLOWED_NEXT}

ВАЖНО ПРО НАБОР СТАТУСОВ:
- Список ДОПУСТИМЫХ зависит от текущего статуса вакансии — это state machine. Если в сообщении есть сигнал, который нельзя передать ни одним из ДОПУСТИМЫХ статусов (например, HR пишет «вы прошли собес» а в списке нет In Progress), выбирай ближайший по смыслу из ДОПУСТИМЫХ.
- Если в ДОПУСТИМЫХ есть значение, совпадающее с ТЕКУЩИМ СТАТУСОМ — это твой no-op вариант: возвращай его, когда сообщение HR'а не несёт новой информации о смене этапа (короткое «спасибо», «понял», уточнение мелкой детали без решения).

Должен вернуть ТОЛЬКО JSON-объект с двумя полями:
- status: ровно одно из значений из списка ДОПУСТИМЫХ выше
- explanation: короткое (1-2 предложения) пояснение на языке пользователя — {USER_LANGUAGE}, на каком бы языке ни писал HR. КРАТКО ПЕРЕСКАЖИ СВОИМИ СЛОВАМИ ключевую идею ответа HR. Не цитируй текст дословно, не выдумывай слова и формулировки, которых в исходном сообщении нет.

Расшифровка ВСЕХ возможных статусов (некоторые могут отсутствовать в твоём списке ДОПУСТИМЫХ — игнорируй такие):
- Applied — кандидат впервые ответил на вакансию и ждёт реакции HR. (Стартовое состояние, обычно не возвращается классификатором — только как no-op для current=Applied.)
- Answered — HR впервые ответил без явного решения (поблагодарил, запросил резюме, уточняет мелкие детали без приглашения и без тестового). Это «первичное знакомство»: после Applied или после долгого молчания HR.
- Invitation — HR приглашает на интервью / собеседование / созвон, обычно с конкретным временем или предложением подобрать слот.
- Test — HR прислал именно тестовое задание / ТЗ как отдельный артефакт: ссылку на платформу с задачей, файл, развёрнутый текст ТЗ, обычно с дедлайном. Переход в Test возможен, только когда само задание уже в сообщении — реальная ссылка на него, приложенный файл или его текст. Файлов ты не видишь: слова HR, что задание приложено или отправлено файлом, считаются присланным заданием. Упоминание тестового без самого задания (HR спрашивает, готов ли кандидат выполнить тестовое, или сообщает, что оно будет) → Answered или ТЕКУЩИЙ СТАТУС как no-op. Скрининговые вопросы про опыт кандидата («расскажите о себе», «опишите последний проект», «какие технологии знаете», «ваш уровень английского», «ожидания по зарплате», «готовы ли к переезду», «когда готовы выйти») — это НЕ Test, это Answered. Просьба ответить на список вопросов из самой вакансии (квалификационный опросник) — тоже Answered, а не Test.
- In Progress — HR подтверждает получение ответа кандидата (сданного теста, прошедшего собеса) и говорит «обсудим внутри / вернёмся с фидбеком / будем думать». То есть мяч у HR, кандидат ждёт.
- Offer — HR делает оффер: предлагает позицию с условиями (зарплата, формат, дата выхода).
- Decline — HR закрыл вопрос по этой вакансии («не подходите», «приняли решение не двигаться дальше», вежливый отказ, отказ после теста/собеса). Сюда же смягчённый отказ, где решение спрятано за похвалой: «отзыв положительный, но на позицию уже есть финалисты», «вакансию закрыли», «взяли другого кандидата», «останемся на связи, вернёмся, если появится подходящее» — когда сама позиция уже занята или закрыта. Пауза найма — тоже вежливый отказ: «вакансию поставили на стоп», «набор заморожен», «ждём бюджета», «бюджет откроют в новом квартале», «вернёмся, когда возобновим» → Decline, даже с обещанием вернуться к кандидату.
- Ghosting — НЕ возвращай этот статус НИКОГДА. Он выставляется отдельным таймером по факту молчания HR, а не по содержанию его сообщений.

Правила выбора при неоднозначности:
- Если в сообщении несколько сигналов — выбирай самый продвинутый по воронке: Offer > Invitation > Test > In Progress > Decline > Answered.
- Приглашение на созвон, встречу или интервью, назначаемое сейчас → Invitation (если в ДОПУСТИМЫХ). Созвон, обещанный после другого шага (тестового, решения команды), статус не решает — решает этот шаг.
- «Готовы предложить позицию» / «хотим сделать оффер» с конкретными условиями → Offer (если в ДОПУСТИМЫХ).
- Отправка текста тестового / ссылки на платформу с тестовым / отдельного описания задачи (обычно с дедлайном или критериями оценки) → Test (если в ДОПУСТИМЫХ). Скрининговые вопросы HR про бэкграунд кандидата → Answered, не Test.
- «Спасибо, обсудим внутри / вернёмся с фидбеком / будем думать» после теста или собеса → In Progress (если в ДОПУСТИМЫХ).
- Позиция для кандидата закрыта («уже есть финалисты», «вакансия закрыта», «выбрали другого») → Decline (если в ДОПУСТИМЫХ), даже когда рядом стоят похвала, «положительная обратная связь» и обещание держать в курсе. Решает судьба этой вакансии, а не тон письма: «останемся на связи» после закрытой позиции — это не In Progress, ждать по ней уже нечего. Это правило сильнее порядка воронки выше: похвала теста или собеса рядом с закрытой позицией не делает письмо In Progress. Пауза найма приравнивается к закрытой позиции: «набор заморожен», «вакансию поставили на стоп», «ждём бюджета», «вернёмся к вам, когда вакансию возобновят» → Decline (если в ДОПУСТИМЫХ): пауза найма на практике означает вежливый отказ. Спрашивай себя об одном: идёт ли найм на это место сейчас — или место занято другим, закрыто либо поставлено на паузу. Если в том же сообщении назначается следующий шаг (созвон, тестовое, оффер) — найм идёт: решает этот шаг, а не слова о бюджете или паузе.
- HR впервые отвечает на отклик без решения → Answered (если в ДОПУСТИМЫХ).
- Текст пустой / бессмысленный / непонятен → no-op (вернуть ТЕКУЩИЙ СТАТУС, если он в ДОПУСТИМЫХ).

Никогда не возвращай статусы, которых нет в списке ДОПУСТИМЫХ. Не переводи названия статусов ни на какой язык.

Примеры (для каждого условно показан ТЕКУЩИЙ СТАТУС и ДОПУСТИМЫЕ — твой случай может отличаться, ориентируйся по логике; язык пользователя в примерах — русский):

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "К сожалению, на текущий момент мы выбрали другого кандидата. Спасибо за интерес!"
Ответ: {"status": "Decline", "explanation": "HR сообщает, что выбран другой кандидат — это вежливый отказ."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Привет! Наш CTO готов созвониться завтра в 15:00, удобно?"
Ответ: {"status": "Invitation", "explanation": "HR приглашает на созвон с CTO с конкретным временем."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Прикладываю тестовое задание. Срок выполнения — 5 дней."
Ответ: {"status": "Test", "explanation": "HR прислал тестовое задание со сроком."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Спасибо за отклик! Передал ваше резюме на рассмотрение, ответим в течение недели."
Ответ: {"status": "Answered", "explanation": "HR подтвердил получение отклика без конкретного решения."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Здравствуйте! Прежде чем двигаться дальше: есть ли действующая медкнижка, работали ли с пароконвектоматом, какой график вам удобен?"
Ответ: {"status": "Answered", "explanation": "HR задаёт скрининговые вопросы про опыт и ожидания — это первичное знакомство, не тестовое задание."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Привет! Ответьте, пожалуйста, на вопросы из вакансии: 1) опыт ведения складского учёта 2) есть ли права категории C 3) готовность к переезду в город B1 4) ожидания по оплате."
Ответ: {"status": "Answered", "explanation": "HR просит ответить на квалификационный опросник из вакансии — это скрининг, не тестовое задание."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Готовы предложить вам позицию ведущего флориста с зарплатой 1800$ нетто, график 5/2, выход 15 ноября."
Ответ: {"status": "Offer", "explanation": "HR делает оффер с указанной позицией, зарплатой, графиком и датой выхода."}

[CURRENT=Test, ALLOWED=In Progress, Offer, Decline]
Текст: "Спасибо за решение, передал команде, вернёмся с фидбеком в течение нескольких дней."
Ответ: {"status": "In Progress", "explanation": "HR подтвердил получение тестового и взял время на ревью — мяч на стороне HR."}

[CURRENT=Invitation, ALLOWED=In Progress, Offer, Decline]
Текст: "Спасибо за интервью, нам было интересно. Обсудим с командой и вернёмся с решением."
Ответ: {"status": "In Progress", "explanation": "HR поблагодарил за собеседование и взял время на принятие решения."}

[CURRENT=In Progress, ALLOWED=Invitation, Test, Offer, Decline]
Текст: "Давайте назначим финальное интервью с CTO на пятницу в 16:00."
Ответ: {"status": "Invitation", "explanation": "HR назначает финальное интервью с CTO с конкретным временем."}

[CURRENT=In Progress, ALLOWED=Invitation, Test, Offer, Decline]
Текст: "Спасибо, ещё немного подождите, обсуждаем."
Ответ: {"status": "In Progress", "explanation": "HR просит подождать — нет смены этапа, no-op."}

[CURRENT=Test, ALLOWED=In Progress, Offer, Decline]
Текст: "К сожалению, по результатам тестового задания решили не двигаться дальше."
Ответ: {"status": "Decline", "explanation": "HR отказал по результатам тестового задания."}

[CURRENT=Answered, ALLOWED=Invitation, Test, Offer, Decline]
Текст: "Коллеги вернулись с положительной обратной связью. Однако на позицию, на которую вы претендовали, уже есть финалисты. Предлагаю оставаться на связи, есть вероятность, что будем расширять команду, я буду держать в курсе."
Ответ: {"status": "Decline", "explanation": "HR хвалит отзыв команды, но на позицию уже есть финалисты — дальше по этой вакансии кандидата не ведут."}

[CURRENT=Test, ALLOWED=In Progress, Offer, Decline]
Текст: "Тестовое посмотрели, всё хорошо. Но у нас заморозили набор до нового квартала — как откроют бюджет, вернёмся к вам по этой же позиции."
Ответ: {"status": "Decline", "explanation": "HR доволен тестовым, но набор заморожен до нового квартала — пауза найма означает вежливый отказ."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Hi! Unfortunately we've decided to move forward with another candidate. Best of luck with your search!"
Ответ: {"status": "Decline", "explanation": "HR сообщает, что выбрали другого кандидата, — вежливый отказ."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Could we hop on a quick 30-min call tomorrow at 4pm CET to chat about the role?"
Ответ: {"status": "Invitation", "explanation": "HR зовёт на получасовой вводный созвон в конкретное время."}

[CURRENT=Test, ALLOWED=In Progress, Offer, Decline]
Текст: "Got the assignment, looks great at first glance — we'll review internally and reach out by Friday."
Ответ: {"status": "In Progress", "explanation": "HR получил тестовое и обещал ответ к пятнице — мяч на стороне HR."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "We'd like to offer you the Lead Florist position at €3200/month, full-time, starting Nov 15. Please confirm."
Ответ: {"status": "Offer", "explanation": "HR делает оффер с позицией, зарплатой, графиком и датой выхода."}

[CURRENT=Applied, ALLOWED=Answered, Invitation, Test, Offer, Decline]
Текст: "Hätten Sie Lust auf ein 30-minütiges Gespräch morgen um 14:00 Uhr CET, um die Stelle zu besprechen?"
Ответ: {"status": "Invitation", "explanation": "HR зовёт на получасовой разговор о вакансии в конкретное время."}

Формат ответа строго: {"status": "...", "explanation": "..."}
""" + ONLY_JSON + """ Никаких пояснений вне поля explanation."""


def _parse_classification(answer: str) -> Classification | None:
    data = json_object(answer, logger, "classify_hr_reply")
    if data is None:
        return None

    raw_status = str_or_none(data.get("status"))
    if raw_status is None:
        return None
    normalized = raw_status.lower()
    status = next(
        (m for m in VacancyStatus if m.value.lower() == normalized),
        None,
    )
    if status is None:
        return None

    return Classification(
        status=status, explanation=str_or_none(data.get("explanation"))
    )


def _allowed_next(current_status: VacancyStatus) -> set[VacancyStatus]:
    """Статусы, из которых модели разрешено выбирать.

    Разрешённые переходы плюс сам нынешний статус как «ничего не
    изменилось», минус «пропал без вести» — его ставит только таймер
    молчания, и модели предлагать его нельзя.

    Порядок двух последних шагов значим: вычеркни «пропал без вести» после
    того, как добавлен нынешний статус, и по вакансии, уже стоящей в нём,
    наставление перечислило бы его среди допустимых — вопреки собственной
    расшифровке статусов, где он запрещён навсегда. Вреда от такого ответа
    нет (граф переходов его гасит), но зов модели тратится впустую.

    Набором, а не строкой: тем же набором ответ модели и сверяется. Сверяй
    его со всем перечнем статусов — и вычеркнутый отсюда проходил бы
    насквозь, а вычёркивали его не для красоты наставления.
    """
    allowed = set(ALLOWED_AUTO_TRANSITIONS[current_status])
    allowed.add(current_status)
    allowed.discard(VacancyStatus.GHOSTING)
    return allowed


def _as_line(allowed: set[VacancyStatus]) -> str:
    """Разрешённые статусы одной строкой; порядок ровный ради наставления."""
    return ", ".join(s.value for s in sorted(allowed, key=lambda s: s.value))


@dataclass(frozen=True)
class HrReplyAsk:
    """Что разбирать: пачку писем HR, нынешний статус вакансии и язык
    пояснения — язык человека, решённый `domain/language_choice`: пояснение к
    смене статуса читает он."""

    text: str
    current_status: VacancyStatus
    language: str


def _classify_request(ask: HrReplyAsk, text: str, allowed_str: str) -> ChatRequest:
    """Что спросить у модели: правила разбора и сама переписка как данные."""
    system_prompt = in_user_language(
        CLASSIFY_HR_REPLY_PROMPT_TEMPLATE
        .replace("{CURRENT_STATUS}", ask.current_status.value)
        .replace("{ALLOWED_NEXT}", allowed_str),
        ask.language,
    )
    user_content = external_block(
        text,
        "сообщения HR-а",
        "Верни только JSON-вердикт по правилам system prompt'а.",
    )
    return ChatRequest(
        purpose="classify_hr_reply",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=MAX_CLASSIFY_TOKENS,
    )


async def classify_hr_reply(
    ask: HrReplyAsk, client: httpx.AsyncClient, model: str,
) -> tuple[Classification | None, str | None]:
    """Классифицирует burst HR-сообщений с учётом текущего статуса вакансии.

    Отвечает парой: вердикт и причина, по которой спросить не вышло. Пустой
    вердикт с пустой причиной значит «модель ответила, а вердикта в ответе
    нет»; причина — что модель не отвечала вовсе. Разводить их обязательно:
    пачка к мигу зова уже вынута из копилки, повторов у разбора нет, и
    схлопнутые в одно, эти два случая теряли письма на всякой заминке
    поставщика. Тем же способом отвечает разбор вакансии и вердикт о
    пригодности.

    Модели дают только те статусы, куда переход разрешён из нынешнего
    (`_allowed_next`): выбирая из них, она не порождает вердиктов, которые
    `apply_classification` всё равно отобьёт. Тем же набором ответ и
    сверяется — наставление держит модель, но не связывает.

    Оборванный на пределе токенов ответ вердиктом не считается: статусы
    терминальны, и приглашение, записанное отказом из недоговорённого ответа,
    человек уже не увидит.
    """
    if not ask.text:
        return None, None
    allowed = _allowed_next(ask.current_status)
    allowed_str = _as_line(allowed)
    # Обрезается начало, а не конец: решает последняя реплика, а первые в
    # пачке — «здравствуйте» и «спасибо».
    text = ask.text[-4000:]
    logger.debug(
        "classify_hr_reply: %d chars, current=%s, allowed=%s",
        len(text), ask.current_status.value, allowed_str,
    )
    request = _classify_request(ask, text, allowed_str)
    reply = await chat(client, model, request, logger)
    if reply.text is None:
        return None, reply.error
    if reply.finish_reason == CUT_BY_LIMIT:
        logger.warning("classify_hr_reply: ответ оборван, вердикта нет")
        return None, None
    parsed = _parse_classification(reply.text)
    if parsed is None:
        log_unparseable(reply.text, logger, "classify_hr_reply")
        return None, None
    if parsed.status not in allowed:
        logger.warning(
            "classify_hr_reply: статус %s модели не предлагали, вердикта нет",
            parsed.status.value,
        )
        return None, None
    logger.debug("classify_hr_reply: status=%s", parsed.status.value)
    return parsed, None

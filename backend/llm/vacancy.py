"""Разбор объявления о вакансии в структурированные поля."""


import logging
import re
from dataclasses import replace

import httpx

from adapters.lm_chat import ChatRequest, chat
from backend.domain.taxonomy import GRADES, WORK_FORMATS
from backend.domain.telegram_identity import normalize_username
from backend.payloads import ParsedVacancy

from backend.incoming import normalize_enum
from backend.llm.answers import (
    ONLY_JSON,
    json_object,
    read_with_a_second_try,
    str_or_none,
)
from backend.llm.candidate import format_known_skills
from backend.llm.rules import (
    WRAPPER_LINE,
    VACANCY_TEXT_CHARS,
    AGGREGATOR_HOSTS_LINE,
    APPLY_CONTACTS,
    FORMAT_MARKERS,
    GEO_LIMIT_MARKERS,
    GRADE_MARKERS,
    RESUME_MARK_LINE,
)
from backend.llm.external import external_block
from backend.llm.skills import clean_stack_items

logger = logging.getLogger(__name__)

# Потолок токенов на разбор объявления и запас на второй заход. Первый заход
# идёт обычным потолком: платить за запас на каждом посте незачем, длинных
# среди них меньшинство. Оборвавшийся ответ переспрашивается с запасом — см.
# `answers.wants_more_room`, — и если не хватило и его, разбор сдаётся, а
# зовущий записывает строку с названной причиной вместо вечного перебора.
MAX_PARSE_TOKENS = 1200
ROOMIER_PARSE_TOKENS = 2400


PARSE_VACANCY_PROMPT = """Ты парсишь пост с вакансией из Telegram-канала и извлекаешь структурированные поля в JSON.

ПЕРЕД ТЕМ КАК ОТВЕТИТЬ — мысленно ПРОЙДИСЬ ПО ЭТОМУ СПИСКУ ВОПРОСОВ. На каждый вопрос ищи ответ ИМЕННО В ПРИСЛАННОМ ТЕКСТЕ; если в тексте ответа нет — пиши null (или [] для stack_required / stack_preferred). Не выдумывай факты.

1. ЛОКАЦИЯ. Где ФИЗИЧЕСКИ должен находиться кандидат? Указан ли город? Страна? Регион? Если в тексте сказано про офис/гибрид — это однозначно про местоположение работы. Если remote с гео-ограничением ("Удалённо в России", "remote from EU") — это тоже локация.
2. ФОРМАТ. Удалёнка / Гибрид / Офис? В тексте ДОЛЖНО быть прямое упоминание формата: """ + FORMAT_MARKERS + """. Если ни одного — null.
3. КОНТАКТ. КАК откликаться по этой вакансии? Это самый важный вопрос — ИЩИ ВНИМАТЕЛЬНО, обычно контакт в самом конце поста. Контактом считается ЛЮБОЙ из вариантов: """ + APPLY_CONTACTS + """.
   Telegram-контакт сохраняется в hr_contact. Любой НЕ-Telegram способ отклика (email / форма / job-площадка / careers-сайт) сохраняется в other_contact ДОСЛОВНО как написано в посте — одной строкой, и это ОБЯЗАТЕЛЬНО адрес: почта, ссылка, домен или телефон. Подпись ссылки или кнопки («Откликнуться», «Подробнее», «Тут», «Apply») и указание словами («пишите в комментарии», «пишите автору поста») адресом НЕ являются — по ним откликнуться нельзя, и other_contact в таком случае null. НО: за подписью ссылки часто идёт её адрес в круглых скобках — «контакты в описании (https://acme.com/jobs)», «Откликнуться (https://forms.gle/abc)». Это настоящий способ отклика, и в other_contact идёт ТОЛЬКО адрес из скобок, без подписи перед ним. Если способов несколько — выбирай тот, который явно обозначен как «куда слать резюме / куда откликаться»; если все равноправны — бери первый встретившийся. Если ВООБЩЕ никакого способа отклика не нашёл — это серьёзный сигнал, что пост — не вакансия (реклама/дайджест/мем); и hr_contact, и other_contact в таком случае null.
4. ГРЕЙД. Уровень кандидата указан явно? Только эти маркеры: """ + GRADE_MARKERS + """. Сами значения поля: """ + ", ".join(GRADES) + """. Если в вакансии нет ни одного из них (характерно, например, для не-IT ролей) — null.
5. СТЕК. Какие навыки/инструменты/технологии/материалы/программы перечислены в тексте (в зависимости от профессии)? Раздели их на ДВА списка: stack_required и stack_preferred. В списки идут НАЗВАНИЯ в именительном падеже, а не требования целиком: слова-обёртки снимаются. Полные правила — ниже в семантике полей.
6. КОМПАНИЯ. Указано ли название работодателя? Корпоративный сайт?
7. ЗАРПЛАТА. Указана ли вилка / уровень зарплаты?

После этого — собирай JSON.

Возвращай ТОЛЬКО валидный JSON-объект следующей формы:
{
  "title": "string",
  "description": "string | null",
  "company_name": "string | null",
  "company_website": "string | null",
  "hr_contact": "string | null",
  "other_contact": "string | null",
  "stack_required": ["string", ...],
  "stack_preferred": ["string", ...],
  "grade": "junior | middle | senior | lead | null",
  "salary": "string | null",
  "remote": "remote | hybrid | office | null",
  "location": "string | null"
}

Семантика полей:
- title: основная роль/должность как в посте ("Senior Frontend Developer", "UX/UI дизайнер", "Marketing Manager", "Флорист"). Без эмодзи, без скобок с названием компании.
- description: развёрнутое саммари вакансии ВСЕГДА НА РУССКОМ ЯЗЫКЕ, каким бы ни был язык поста (English post → русское саммари; Deutsch → русское саммари), 3-6 предложений, своими словами. Цель — дать читателю достаточно контекста, чтобы он понимал суть позиции, не открывая исходный пост. Покрывай по возможности: тип роли и грейд, домен/индустрию или продукт компании, ключевые задачи и зону ответственности, важные инструменты/материалы/стек (особенно нестандартные для роли), формат работы и гео-ограничения, любые заметные особенности (масштаб, размер команды, специфика проекта). НЕ навязывай тех-вокабуляр, если вакансия не техническая — используй язык домена самой вакансии (IT, дизайн, маркетинг, торговля, общепит, образование, медицина, ручной труд, искусство, спорт и т.п.). Не цитируй дословно, не выдумывай факты, которых нет в тексте. Не повторяй то, что уже есть в других полях JSON в виде голого перечисления (стек, зарплата, формат) — упоминай их только как часть связного рассказа. Если пост не описывает конкретную открытую вакансию (реклама, дайджест, мем, анонс митапа, обрывок, ПОСТ СОИСКАТЕЛЯ) — null.
- company_name: реальное название компании если упомянуто, иначе null. Не заполняй обобщённые "стартап", "ИП", "ООО".
- company_website: корпоративный сайт компании-работодателя если упомянут в посте. Формат — URL целиком ("https://techcorp.com") или домен ("techcorp.com"). Это ИМЕННО сайт компании-работодателя. НЕЛЬЗЯ записывать сюда: ссылки на канал публикации (t.me/...), ссылки на HR (@username, t.me/username), ссылки на общие хосты — job-площадки, соцсети, мессенджеры, хостинги анкет и сокращатели ({AGGREGATOR_HOSTS} и т.п.), ссылки на чаты/сообщества, телеграм-боты для отклика. Если корпоративный сайт не упомянут — null.
- hr_contact: одна строка вида "@username" или "t.me/username" — контакт того, кому слать резюме. Если в посте несколько ссылок — выбирай тот, что обозначен как контакт HR/рекрутёра ("писать @anna", "резюме — @ivan"). Ссылки на сам канал публикации игнорируй. ВАЖНО: сюда идёт ТОЛЬКО Telegram-контакт. Email/форма/job-площадка/careers-сайт сюда НЕ ПОПАДАЮТ — они идут в other_contact. Если за подписью ссылки стоит её адрес в круглых скобках («писать Анне (https://t.me/anna_hr)») — сюда идёт ТОЛЬКО адрес из скобок, без подписи перед ним. null если Telegram-контакта в посте нет.
- other_contact: одна строка — любой НЕ-Telegram способ откликнуться, дословно как написано в посте, и обязательно АДРЕСОМ: почта, ссылка целиком, домен или телефон. Примеры: "jobs@acme.com", "https://forms.gle/abc123", "hh.ru/vacancy/12345", "careers.openacme.com/apply", "+7 999 123-45-67". Строка без адреса сюда НЕ идёт: подпись ссылки («Откликнуться», «Подробнее», «Apply here») и указание словами («пишите в комментарии под постом») — не контакт, а призыв, и вместо них null. Подпись со стоящим за ней адресом в круглых скобках — контакт: из «контакты в описании (https://acme.com/jobs)» сюда идёт "https://acme.com/jobs", сама подпись отбрасывается. Это ОТДЕЛЬНОЕ от hr_contact поле и заполняется НЕЗАВИСИМО — может быть заполнено и одновременно с hr_contact (когда в посте и TG-контакт, и email/форма), и в одиночку (когда TG-контакта в посте нет). Если способов несколько — выбирай явно обозначенный как «куда слать резюме», иначе — первый встретившийся. null если в посте нет НИКАКОГО НЕ-Telegram способа отклика.
- stack_required и stack_preferred: ДВА массива навыков/инструментов/технологий/материалов/программ УПОМЯНУТЫХ в тексте, разнесённые по тому, обязательно ли это требование вакансии или нет. «Стек» здесь — обобщённое название, оно одинаково применимо к технологиям разработчика (Python, React, PostgreSQL), инструментам дизайнера (Figma, Sketch), маркетинговым платформам (HubSpot, Google Analytics), оборудованию/материалам флориста или мастера, и т.п. Не игнорируй нетехнические скилы — извлекай и их.
  Каждое значение — короткое имя инструмента или навыка БЕЗ ВЕРСИИ, без скобок с уточнениями и без перечисления вариантов внутри одной строки.
  ПАДЕЖ (применяется к ОБЕИМ группам, в любой профессии). Значение пишется в именительном падеже, как название в словаре: «работать с Unix-консолью» → «Unix-консоль», «владеть секатором» → «Секатор», «съёмка на Sony» → «Sony», «ведём отчётность в Excel» → «Excel». Если начальная форма слова тебе не очевидна — бери слово ровно так, как оно написано в посте: падеж из текста лучше выдуманного окончания вроде «консолья» или «секатора».
  НАЗВАНИЕ, А НЕ ТРЕБОВАНИЕ (применяется к ОБЕИМ группам, в любой профессии). Требование вакансии и название навыка — разные вещи, и в стек идёт второе. Слова-обёртки (""" + WRAPPER_LINE + """) в значение НЕ входят никогда — бери то, что стоит за ними, и приводи к именительному падежу:
    «Опыт работы с Docker» → «Docker»; «Опыт монтажа в Premiere Pro» → «Premiere Pro»; «Знание кассовой дисциплины» → «Кассовая Дисциплина»; «Опыт ведения соцсетей» → «Ведение Соцсетей»; «Умение работать с секатором» → «Секатор»; «Понимание основ композиции» → «Композиция».
    Это правило применяется ПОСЛЕДНИМ, когда обе группы уже собраны: пройди по каждому значению обеих групп и сними обёртку, если она осталась. Значение, начинающееся со слова «опыт», «знание», «умение», «навык» или «понимание», в ответе недопустимо.
    Целое требование стек-тегом не бывает: если после снятия обёртки осталась фраза длиннее четырёх слов («продаж строительных материалов в розницу», «ведения переговоров с поставщиками сырья»), в стек она не идёт вовсе — верни только названный в ней инструмент или навык, если он там назван.
  РАЗДЕЛЕНИЕ НА ОБЯЗАТЕЛЬНЫЕ И ЖЕЛАТЕЛЬНЫЕ — ключевое решение. Сначала посмотри, разделило ли их само объявление.
  - РАЗДЕЛЕНИЕ ЕСТЬ — делим по нему, и думать больше не о чем. Оно бывает двух видов, на любом языке и в любом написании. Разделами: требования ("Требования:", "Что нужно от тебя:", "Обязательно:", "Что мы ждём:", "Стек:", "Технологии:", "Инструменты:", "Requirements", "Must have") против пожеланий ("Будет плюсом:", "Что будет плюсом:", "Дополнительно желательно:", "Nice to have", "Preferred", "Bonus"). Пометкой рядом с самим скилом: требуют через "требуется", "обязателен", "должен знать", "уверенное знание", "опыт работы с", "ежедневно работаем с"; желают через "будет плюсом", "плюсом будет", "как преимущество", "приветствуется", "желательно", "знание X — плюс", "is a plus", "preferred", "a bonus, not a requirement", "desirable", "ideally". Требуемое — в stack_required, желаемое — в stack_preferred.
  - РАЗДЕЛЕНИЯ НЕТ — раздели сам, по близости к роли ЭТОЙ вакансии. В stack_required идёт ядро: то, без чего названную в title работу не делают, — основной язык или главный инструмент и то, на чём стоят обязанности. Всё прочее — упомянутое вскользь, соседнее, вспомогательное, названное в рассказе о компании или в перечне обязанностей, — идёт в stack_preferred.
  - БЛИЗОСТЬ СЧИТАЕТСЯ К САМОЙ ВАКАНСИИ, а не к списку известных скилов кандидата: этот список в разделении не участвует вовсе, он только про написание. Пример: Node.js в вакансии Python-разработчика — желательный, потому что роль другая; в вакансии Node-разработчика тот же Node.js — ядро, и он обязательный.
  - ПРЕДЕЛ ОБЯЗАТЕЛЬНЫХ, когда делишь сам: их не больше, чем max(5, половина всех строк стека). Насчитал больше — оставь в stack_required самые близкие к роли, остальные переведи в stack_preferred. Считай по готовым спискам, после снятия обёрток и склейки повторов.
  - ОДИН СКИЛЛ — ОДНА ГРУППА. Один и тот же скилл НЕ должен встречаться одновременно в stack_required и stack_preferred. Назван в обеих — оставь в stack_required, из stack_preferred убери. Речь именно об одном скиле, названном дважды: два РАЗНЫХ инструмента остаются двумя строками, даже если в списке известных скилов кандидата они стоят алиасами одного скила.
  ВСЕГДА ОТБРАСЫВАЙ ВЕРСИИ И НОМЕРА (правило применяется к ОБЕИМ группам): любые цифры/числа после имени (через пробел или точку), суффиксы "+", "v2" — отбрасывай. Примеры формы: "<имя> 3.13" → "<имя>", "<имя> 17" → "<имя>", "<имя> 20" → "<имя>", "<имя> 14.5" → "<имя>", "<имя> 8" → "<имя>". Это касается любых доменов: версий ПО, версий Adobe-продуктов ("Photoshop 2024" → "Photoshop"), номеров стандартов и т.п.
  КАПИТАЛИЗАЦИЯ (применяется к ОБЕИМ группам). Каждое слово стек-тега должно начинаться с заглавной буквы (например, "Прототипирование", "Микросервисная Архитектура", "Performance Marketing"). ИСКЛЮЧЕНИЕ — бренды/имена с уже зафиксированной формой написания: их сохраняй ровно как принято, не ломай регистр. Сюда относятся бренды из самых разных индустрий, например:
  - IT: "iOS", "gRPC", "C++", "C#", ".NET", "FastAPI", "PostgreSQL", "SQLAlchemy", "ClickHouse", "RabbitMQ", "GitLab", "Node.js", "macOS", "watchOS";
  - дизайн / медиа: "InDesign", "After Effects", "Photoshop", "Illustrator", "Premiere Pro", "DaVinci Resolve", "Cinema 4D", "AutoCAD", "SketchUp";
  - маркетинг / аналитика: "HubSpot", "Mailchimp", "Google Analytics", "AdWords", "Google Ads", "Salesforce", "Power BI", "Tableau";
  - офис / продуктивность: "Notion", "Miro", "FigJam", "Trello", "Jira", "Confluence", "MS Office", "Google Workspace".
  Список не исчерпывающий — для бренда из любой профессии ориентируйся на общеупотребимое написание (как сам бренд пишет себя в логотипе/документации).
  Другая нормализация (применяется к ОБЕИМ группам): из скобки с перечислением в стек идёт ОДНА строка — ни группа с хвостом внутри значения, ни всё перечисленное. Какая именно — решай по порядку: (1) написание, стоящее в списке известных скилов кандидата, именем скила или алиасом, выигрывает всегда; подошло несколько — бери названное в тексте первым; (2) иначе — то, что чаще зовут отдельным навыком, а не описанием («Docker» и «Kubernetes» пишут в резюме, «контейнеризацию» — почти нет); (3) иначе — то, что стоит перед скобкой. Примеры: "SQL (PostgreSQL, MySQL)" → "SQL"; "контейнеризация (Docker, Kubernetes)" → "Docker"; "LLM (GigaChat, ChatGPT, DeepSeek)" → "LLM"; "CRM (HubSpot, Salesforce)" → "CRM"; "Электроинструмент (перфоратор, шуруповёрт)" → "Электроинструмент". Дедуплицируй: если ОДИН И ТОТ ЖЕ инструмент назван в посте разными написаниями («Postgres» и «PostgreSQL», «1С» и «1C») — верни одну строку, тем написанием, каким он назван первым, и в той группе, где встретился первым; пришлись написания на разные группы — строка остаётся в stack_required. Разные инструменты сводить нельзя, даже когда у кандидата они перечислены алиасами одного скила. Не добавляй "общее знание" (вроде Git, Linux, MS Office), если их нет в тексте. [] для группы где ничего не упомянуто.
  Если ниже передан список известных скилов кандидата с их алиасами — сверяй с ним упомянутое в посте и пиши ТЕМ ЖЕ НАПИСАНИЕМ, какое стоит в списке: именем скила, если названо оно, либо его алиасом, если названо то, что стоит в алиасах. Бери БЛИЖАЙШЕЕ написание, а не имя скила поверх алиаса: подмена именем прячет от читателя карточки то, что вакансия требует именно этого инструмента, а не всей группы. Это правило тоже применяется к ОБЕИМ группам. Примеры: скилл "Adobe Suite" с алиасами "Photoshop", "Illustrator", "InDesign" — пост про "нужен Photoshop" даёт "Photoshop", НЕ "Adobe Suite"; скилл "Веб-аналитика" с алиасами "Google Analytics", "Яндекс Метрика" — пост про Метрику даёт "Яндекс Метрика", НЕ "Веб-аналитика"; скилл "Электроинструмент" с алиасами "Перфоратор", "Шуруповёрт" — пост про перфоратор даёт "Перфоратор", НЕ "Электроинструмент".
- grade: уровень кандидата ТОЛЬКО если он явно указан в заголовке или требованиях. Маркеры и значения поля перечислены в вопросе про грейд выше; оттуда же маркеры берёт и вердикт пригодности. Если уровень не указан явно (или вакансия в принципе не оперирует такими маркерами — типично для нетехнических ролей) — null.
- salary: дословно как написано ("$3000-5000", "от 250к net", "по итогам собеса", "по договорённости"). null если не упомянуто.
- remote: формат работы. null если не сказано.
- location: ФОРМАТ СТРОГО — "Страна" или "Страна/Город" через прямой слэш. Применяй ниже.
  Правила формата:
  - Если в тексте указан город — пиши "Страна/Город". Страну сам выводи из города.
  - Если указана только страна/регион без города — пиши только страну.
  - Страна и город — ВСЕГДА ПО-РУССКИ, каким бы ни был язык поста: "Germany, Berlin" → "Германия/Берлин", "USA, New York" → "США/Нью-Йорк", "Yerevan" → "Тверская область/Тверь". Место — не цитата из поста, а значение колонки, по которой идут отбор и статистика: напиши одно и то же место двумя языками, и оно посчитается двумя разными.
  - Не используй сокращений и не используй полных официальных названий — бери общеупотребимую русскую форму: "Россия" (НЕ "РФ", НЕ "Российская Федерация"), "США" (НЕ "Соединённые Штаты Америки"), "Великобритания" (НЕ "Соединённое Королевство"), "Германия" (НЕ "Федеративная Республика Германия").
  - Каждое слово страны/города — С ЗАГЛАВНОЙ БУКВЫ ("Россия/Москва", "США/Сан-Франциско", "Сербия/Нови-Сад", "Япония/Токио").
  Когда что заполнять:
  - Офис/гибрид — указывай локацию офиса ("Россия/Москва", "Германия/Берлин", "Тверская область").
  - Remote С ОГРАНИЧЕНИЕМ ПО ГЕОГРАФИИ кандидата — пиши страну/регион ограничения. Это ВАЖНО для гео-фильтрации. Триггерные формулировки: """ + GEO_LIMIT_MARKERS + """. Тогда location — страна или регион из самой формулировки ("Россия", "ЕС", "СНГ"); для ограничения по часовому поясу бери страну, к которой пояс привязан ("Россия" для MSK).
  - Remote БЕЗ географических ограничений ("можно из любой страны", "worldwide", "remote из любой точки мира") — location=null.
  - Местоположение не упомянуто вообще — null.

ИЗВЕСТНЫЕ СКИЛЫ КАНДИДАТА (формат: имя — алиасы через запятую; сверяй с ним написание значений stack):
{KNOWN_SKILLS_BLOCK}

ПОСТ СОИСКАТЕЛЯ — НЕ ВАКАНСИЯ. Хиринг-каналы вперемешку с вакансиями публикуют посты людей, которые предлагают на работу СЕБЯ. Структурно такой пост почти неотличим от вакансии: названа роль, перечислен стек, есть контакт, иногда формат и локация. Направление обратное, и решает только оно: в вакансии работодатель зовёт кандидата, в посте соискателя автор предлагает себя. Признаки: рассказ о себе от первого лица («у меня N лет опыта», «работал в», «умею», «I have», «I'm looking for»), предложение своего резюме или портфолио, хэштеги """ + RESUME_MARK_LINE + """, отсутствие обязанностей и условий от лица нанимателя. Увидел такое — ВСЕ поля null, включая title. Не пытайся «спасти» такой пост: заполненные по нему поля означают письмо живому человеку от нашего имени.

Правила:
- Только то, что есть в тексте. Не выдумывай.
- Если поле невозможно извлечь — null (или [] для stack_required / stack_preferred).
- title должен быть всегда — это главное поле.
- Никогда не переводи значения enum-полей (grade, remote) на русский.
- """ + ONLY_JSON + """

Примеры:
Текст (английский пост, всё под "Tools" — обязательное; description и location по-русски, каким бы ни был язык поста): "Senior Marketing Manager @AcmeMarketing\\n\\nWe're looking for a strong marketer for our SaaS team. Tools: HubSpot, Google Analytics, Mailchimp, Notion. 5+ years experience.\\nSalary: €4500-6000\\nRemote, EU only.\\nSite: https://acme.io\\nContact: @anna_hr"
Ответ: {"title": "Senior Marketing Manager", "description": "Senior-маркетолог в SaaS-команду AcmeMarketing. От кандидата ждут более пяти лет опыта в маркетинге и уверенной работы с HubSpot, Google Analytics, Mailchimp и Notion. Формат полностью удалённый, но с ограничением: кандидат должен находиться в ЕС. Зарплатная вилка указана в евро, отклик идёт через Telegram-контакт HR.", "company_name": "AcmeMarketing", "company_website": "https://acme.io", "hr_contact": "@anna_hr", "other_contact": null, "stack_required": ["HubSpot", "Google Analytics", "Mailchimp", "Notion"], "stack_preferred": [], "grade": "senior", "salary": "€4500-6000", "remote": "remote", "location": "ЕС"}

Текст (русский пост, всё под "Инструменты" — обязательное; нетехнический домен): "💐 Senior Флорист @BloomCo\\n\\nИщем опытного флориста в студию. Инструменты: секаторы, флористическая лента, оазис, упаковочные материалы. Опыт 5+ лет.\\nЗП: $1500-2200\\nОфис, Тверь.\\nСайт: https://bloomco.am\\nКонтакт: @anna_hr"
Ответ: {"title": "Senior Флорист", "description": "Опытный флорист уровня senior в студию BloomCo. Ожидается опыт от 5 лет, набор инструментов — секаторы, флористическая лента, оазис и упаковочные материалы. Работа в офисе студии в Тверье. Зарплатная вилка обозначена в долларах, контакт для отклика — Telegram HR.", "company_name": "BloomCo", "company_website": "https://bloomco.am", "hr_contact": "@anna_hr", "other_contact": null, "stack_required": ["Секаторы", "Флористическая Лента", "Оазис", "Упаковочные Материалы"], "stack_preferred": [], "grade": "senior", "salary": "$1500-2200", "remote": "office", "location": "Тверская область/Тверь"}

Текст (рядом с InDesign стоит "приветствуется", рядом с After Effects — "будет плюсом" — оба желательные): "Junior дизайнер в команду. Опыт с InDesign приветствуется. After Effects будет плюсом. Гибридный формат, Москва. Резюме на @ivanmail"
Ответ: {"title": "Junior дизайнер", "description": "Позиция junior-дизайнера в команду без жёстких требований к опыту. Базовые ожидания — знакомство с InDesign, плюсом будет After Effects. Формат гибридный, с присутствием в московском офисе. Отклик через Telegram-контакт указанного рекрутёра.", "company_name": null, "company_website": null, "hr_contact": "@ivanmail", "other_contact": null, "stack_required": [], "stack_preferred": ["InDesign", "After Effects"], "grade": "junior", "salary": null, "remote": "hybrid", "location": "Россия/Москва"}

Текст (явное смешанное распределение: блок "Требования:" — required, блок "Будет плюсом:" — preferred): "Бренд-менеджер. Требования: ведение бренд-стратегии, работа с подрядчиками, отчётность. Будет плюсом: опыт с Notion, Miro, английский язык. Удалёнка. @hr_acme"
Ответ: {"title": "Бренд-менеджер", "description": "Бренд-менеджер с обязанностями по ведению бренд-стратегии, работе с подрядчиками и регулярной отчётности. Дополнительными плюсами будут навыки в Notion, Miro и английский язык. Формат работы полностью удалённый. Отклик через Telegram-контакт HR.", "company_name": null, "company_website": null, "hr_contact": "@hr_acme", "other_contact": null, "stack_required": ["Бренд-стратегия", "Работа С Подрядчиками", "Отчётность"], "stack_preferred": ["Notion", "Miro", "Английский Язык"], "grade": null, "salary": null, "remote": "remote", "location": null}

Текст (английский пост, фронтенд-вакансия; React и Next.js — разные инструменты, и обе строки остаются, хотя у кандидата Next.js стоит алиасом React; description всё равно русский): "Frontend Engineer for a product team. Stack: TypeScript, React, Next.js, Tailwind, Docker. Remote."
Ответ: {"title": "Frontend Engineer", "description": "Frontend-инженер в продуктовую команду. Основа стека — TypeScript и React поверх Next.js, Tailwind для вёрстки и Docker для окружения. Формат полностью удалённый, географических ограничений в посте нет. Telegram-контакта в посте тоже нет.", "company_name": null, "company_website": null, "hr_contact": null, "other_contact": null, "stack_required": ["TypeScript", "React", "Next.js", "Tailwind", "Docker"], "stack_preferred": [], "grade": null, "salary": null, "remote": "remote", "location": null}

Текст (нон-IT: три инструмента одного пакета — три отдельные строки; список известных скилов кандидата на это не влияет, даже если все три стоят там алиасами скила "Adobe Suite"): "Senior графический дизайнер в студию. Что нужно: Photoshop, Illustrator, InDesign, типографика. Удалёнка. @hr_studio"
Ответ: {"title": "Senior графический дизайнер", "description": "Senior графический дизайнер в студию. Обязательные навыки — работа с пакетом Adobe (Photoshop, Illustrator, InDesign) и типографика. Формат полностью удалённый. Отклик через Telegram-контакт HR.", "company_name": null, "company_website": null, "hr_contact": "@hr_studio", "other_contact": null, "stack_required": ["Photoshop", "Illustrator", "InDesign", "Типографика"], "stack_preferred": [], "grade": "senior", "salary": null, "remote": "remote", "location": null}

Текст (вакансия дизайнера, явные маркеры обязательности — "требуется/обязателен" — required): "UX/UI дизайнер в Acme. acme.io — продуктовая студия. Требуется Figma, обязателен опыт с прототипированием. Резюме @hr_acme"
Ответ: {"title": "UX/UI дизайнер", "description": "UX/UI дизайнер в продуктовую студию Acme. Основные требования — уверенная работа в Figma и обязательный опыт прототипирования. Компания позиционирует себя как продуктовая студия. Формат работы в посте явно не указан, отклик через Telegram-контакт HR.", "company_name": "Acme", "company_website": "acme.io", "hr_contact": "@hr_acme", "other_contact": null, "stack_required": ["Figma", "Прототипирование"], "stack_preferred": [], "grade": null, "salary": null, "remote": null, "location": null}

Текст (контакт — email и форма, БЕЗ Telegram; hr_contact=null, other_contact=email; вакансия валидна; всё под "Что нужно:" → required): "Marketing Manager в OpenAcme. Удалёнка из любой точки мира. Что нужно: HubSpot, Google Analytics, ведение performance-кампаний. Резюме на jobs@openacme.com или через форму на careers.openacme.com/apply"
Ответ: {"title": "Marketing Manager", "description": "Marketing-менеджер в компанию OpenAcme на полностью удалённый формат без географических ограничений. Среди обязательных скилов — HubSpot, Google Analytics и опыт ведения performance-кампаний. Telegram-контакта в посте нет, отклик через корпоративный email или форму на careers-сайте.", "company_name": "OpenAcme", "company_website": "careers.openacme.com", "hr_contact": null, "other_contact": "jobs@openacme.com", "stack_required": ["HubSpot", "Google Analytics", "Performance Marketing"], "stack_preferred": [], "grade": null, "salary": null, "remote": "remote", "location": null}

Текст (удалёнка С ограничением по гео — обязательно фиксируй ограничение в location, страну пиши общеупотребимо; набор скилов под "Что нужно:" → required): "Customer Success Manager\\nЛокация: Удалённо в РФ\\nКомпания: КА https://example.com\\nЧто нужно: ведение клиентов, отчётность, Intercom. Резюме @veronikavlasovets"
Ответ: {"title": "Customer Success Manager", "description": "Customer Success Manager в команду через кадровое агентство. Обязанности — ведение клиентов, регулярная отчётность, работа в Intercom. Формат удалённый, но с обязательной локацией в России — важное гео-ограничение для кандидата. Отклик через Telegram-контакт рекрутёра.", "company_name": "КА", "company_website": "https://example.com", "hr_contact": "@veronikavlasovets", "other_contact": null, "stack_required": ["Ведение Клиентов", "Отчётность", "Intercom"], "stack_preferred": [], "grade": null, "salary": null, "remote": "remote", "location": "Россия"}

Текст (английский пост, зарубежный город → 'Страна/Город' всё равно по-русски; набор скилов под "Tools:" → required): "Senior Product Designer at Acme Berlin. Hybrid, 2 days in the office. Tools: Figma, Sketch. CV to jobs@acme.de"
Ответ: {"title": "Senior Product Designer", "description": "Senior product designer в берлинский офис Acme. Основные инструменты — Figma и Sketch. Формат гибридный, с обязательными двумя днями в офисе: подразумевается переезд или готовность работать из Берлина. Telegram-контакта нет, отклик идёт через корпоративную почту.", "company_name": "Acme", "company_website": null, "hr_contact": null, "other_contact": "jobs@acme.de", "stack_required": ["Figma", "Sketch"], "stack_preferred": [], "grade": "senior", "salary": null, "remote": "hybrid", "location": "Германия/Берлин"}

Текст (один скилл — отдельной строкой "nice to have" → preferred; остальные под "Требования:" → required): "Senior SMM-менеджер. Требования: ведение соцсетей бренда, контент-план, аналитика. Nice to have: Canva. Удалёнка. @hr_anna"
Ответ: {"title": "Senior SMM-менеджер", "description": "Senior SMM-менеджер с обязанностями по ведению соцсетей бренда, формированию контент-плана и аналитике результатов. Дополнительным плюсом будет Canva. Формат полностью удалённый. Отклик через Telegram-контакт HR.", "company_name": null, "company_website": null, "hr_contact": "@hr_anna", "other_contact": null, "stack_required": ["Ведение Соцсетей", "Контент-План", "Аналитика"], "stack_preferred": ["Canva"], "grade": "senior", "salary": null, "remote": "remote", "location": null}

Текст (пост соискателя: роль, стек и контакт на месте, но автор предлагает СЕБЯ — все поля null, включая title): "#cv #python #django #backend\\n\\nПозиция: Python Developer / Backend Developer\\nФормат: только удалённо\\nЗанятость: краткосрочные фриланс-заказы\\nЧто могу: Django, DRF, PostgreSQL, Telegram-боты. Опыт 4 года.\\nКонтакты: Telegram: @nnekojiru"
Ответ: {"title": null, "description": null, "company_name": null, "company_website": null, "hr_contact": null, "other_contact": null, "stack_required": [], "stack_preferred": [], "grade": null, "salary": null, "remote": null, "location": null}

Текст (тот же случай без единого хэштега — решает направление, а не метки): "Ищу работу QA-инженером. 5 лет в мобильном тестировании, Appium, Charles, Postman. Готов к удалёнке, рассмотрю part-time. Резюме вышлю в личку — @tester_ann"
Ответ: {"title": null, "description": null, "company_name": null, "company_website": null, "hr_contact": null, "other_contact": null, "stack_required": [], "stack_preferred": [], "grade": null, "salary": null, "remote": null, "location": null}

Текст: "Дайджест вакансий недели. Подборка лучших предложений в IT и дизайне."
Ответ: {"title": null, "description": null, "company_name": null, "company_website": null, "hr_contact": null, "other_contact": null, "stack_required": [], "stack_preferred": [], "grade": null, "salary": null, "remote": null, "location": null}

Текст: "🚀 Сигнал! Покупаем монету $XYZ прямо сейчас, +300% за день. Подписка на канал — t.me/pump_signals"
Ответ: {"title": null, "description": null, "company_name": null, "company_website": null, "hr_contact": null, "other_contact": null, "stack_required": [], "stack_preferred": [], "grade": null, "salary": null, "remote": null, "location": null}

Текст: "Друзья, кто-то знает хорошего бариста в Тбилиси? Обсуждение в комментариях."
Ответ: {"title": null, "description": null, "company_name": null, "company_website": null, "hr_contact": null, "other_contact": null, "stack_required": [], "stack_preferred": [], "grade": null, "salary": null, "remote": null, "location": null}"""


# Sanitiser для company_name: иногда LLM прилепляет URL прямо в название
# («КА https://example.com/», «Brand foo.com»). Регексп ловит trailing
# URL/домен и вырезает; в `parsed_vacancy_from_json` вырезанный URL уезжает в
# company_website если оно пусто.
_TRAILING_URL_RE = re.compile(
    r"\s*(https?://[^\s)]+|(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s)]*)?)\)?\s*$"
)


# Sanitiser для other_contact: пост часто кончается ссылкой-словом
# («Откликнуться», «Подробнее»), и способ отклика приезжает подписью. Адрес к
# ней теперь подставляет чтение поста (`extract_post_text`), но подставить
# нечего, когда ссылки нет вовсе, — а «пишите в комментарии» модель приносит
# как контакт и без неё. Такая подпись уходила в заметку вакансии строкой
# «Контакты: Откликнуться»: контакт вроде бы есть, а откликаться по нему
# некуда. Настоящий способ отклика узнаётся по адресу внутри строки — почте,
# ссылке, домену, телефону.
_CONTACT_ADDRESS_RE = re.compile(
    r"""
      [^\s@]+@[^\s@]+\.[a-zA-Z]{2,}                     # почта
    | https?://\S+                                      # ссылка целиком
    | (?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/\S*)?    # домен
    | \+?\d[\d\s()-]{7,}\d                              # телефон
    """,
    re.VERBOSE,
)

# Адрес, дописанный за подписью ссылки при чтении поста (`extract_post_text`).
# Модель приносит их вместе — «контакты в описании (https://acme.com/jobs)», — а
# в заметку вакансии нужен способ отклика, а не пересказ поста.
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
    ника не разобрать, ни в заметке вакансии не откликнуться.

    Адрес внутри обычной фразы это не задевает: скобок там нет, и фраза
    остаётся дословной.
    """
    labelled = _LABELLED_ADDRESS_RE.search(value)
    if labelled and _CONTACT_ADDRESS_RE.fullmatch(labelled.group(1)):
        return labelled.group(1)
    return value


def _hr_contact(hr_contact: str | None) -> str | None:
    """Контакт собеседника без подписи, если адрес пришёл в скобках за ней.

    Заслона на «строку без адреса» здесь нет и не нужно: ник приводит
    `normalize_username`, и на не-контакте он даёт пустоту сам.
    """
    return _address_after_label(hr_contact) if hr_contact else hr_contact


def _way_to_apply(other_contact: str | None) -> str | None:
    """Оставить способ отклика, только если в нём есть адрес.

    Строка без почты, ссылки, домена или телефона — не контакт, а подпись
    кнопки («Откликнуться») или указание словами («пишите в комментарии»).
    Пустоты она не заменяет: заметка вакансии показывает её как контакт, и
    человек идёт по ней в никуда.

    От подписи со своим адресом в скобках остаётся один адрес. Такую пару
    собирает чтение поста, подставляя адрес спрятанной ссылки за её подписью;
    модель приносит её целиком, и записанная как есть, она читалась бы в
    заметке не адресом, а пересказом. Адрес внутри обычной фразы («резюме на
    careers.acme.com/apply») это не задевает: скобок там нет, и фраза остаётся
    дословной.
    """
    if not other_contact:
        return other_contact
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
    return ParsedVacancy(
        title=title,
        description=description,
        company_name=company_name,
        company_website=company_website,
        hr_contact=_hr_contact(_text_field("hr_contact")),
        other_contact=_way_to_apply(_text_field("other_contact")),
        stack_required=stack_required,
        stack_preferred=stack_preferred,
        grade=normalize_enum(data.get("grade"), GRADES),
        salary=_text_field("salary"),
        remote=normalize_enum(data.get("remote"), WORK_FORMATS),
        location=_text_field("location"),
    )


def _parse_request(text: str, known_skills, max_tokens: int) -> ChatRequest:
    """Что спросить у модели: правила разбора и сам пост как данные."""
    system_prompt = PARSE_VACANCY_PROMPT.replace(
        "{KNOWN_SKILLS_BLOCK}", format_known_skills(known_skills)
    ).replace("{AGGREGATOR_HOSTS}", AGGREGATOR_HOSTS_LINE)
    user_content = external_block(
        text,
        "пост из Telegram-канала с вакансией",
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


def _without_channel_as_hr(
    parsed: ParsedVacancy, channel_username: str | None
) -> ParsedVacancy:
    """Убрать из контакта сам канал: это не собеседник, а источник.

    Ник приводится общим правилом, а не своими руками: своими хвост ссылки
    становится ником, и `t.me/канал/1481` даёт «1481».
    """
    contact_username = normalize_username(parsed.hr_contact)
    if (
        channel_username
        and contact_username
        and contact_username.lower() == channel_username.lower()
    ):
        return replace(parsed, hr_contact=None)
    return parsed


def _log_parsed(parsed: ParsedVacancy) -> None:
    logger.debug(
        "parse_vacancy: title=%r company=%r hr=%s other=%s stack_req=%d stack_pref=%d",
        parsed.title,
        parsed.company_name,
        parsed.hr_contact,
        parsed.other_contact,
        len(parsed.stack_required or []),
        len(parsed.stack_preferred or []),
    )


async def parse_vacancy(
    text: str,
    client: httpx.AsyncClient,
    model: str,
    channel_username: str | None = None,
    *,
    known_skills=None,
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
            client, model, _parse_request(text, known_skills, room), logger
        ),
        parsed_vacancy_from_json,
        (MAX_PARSE_TOKENS, ROOMIER_PARSE_TOKENS),
        (logger, "parse_vacancy"),
    )
    if parsed is None:
        return None, trouble
    parsed = _without_channel_as_hr(parsed, channel_username)
    _log_parsed(parsed)
    return parsed, None

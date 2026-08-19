"""Хосты, которые не бывают домашним сайтом компании.

Перечень нужен двоим сразу, и потому живёт здесь, а не у одного из них. Отбор
компаний гасит такой хост до пустоты: сведение по домену на общем хосте
склеило бы всех, кто на нём сидит, — необратимо и без арбитра. Наставления
модели перечисляют те же хосты словами: разбор не должен класть их в поле
сайта компании, а арбитр не должен считать их доводом «сайты разные».

Переписанный своими словами в наставлении, перечень уже расходился с этим:
код знал `gitlab.com` и `avito.ru`, наставление арбитра — нет, зато знало
`xing.com`, которого не было в коде.
"""

AGGREGATOR_HOSTS = frozenset({
    # Агрегаторы вакансий, соцсети, мессенджеры, блог-платформы: ссылка на
    # канал, профиль или пост говорит о компании не больше, чем её отсутствие.
    "t.me",
    "telegram.me",
    "telegram.org",
    "linkedin.com",
    "hh.ru",
    "habr.com",
    "vc.ru",
    "github.com",
    "gitlab.com",
    "avito.ru",
    "superjob.ru",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "vk.com",
    "ok.ru",
    "youtube.com",
    "behance.net",
    "dribbble.com",
    "medium.com",
    "xing.com",
    # Шеринговые хостинги job-страниц и резидент-каталоги: на одном хосте
    # сидит много разных компаний, и `rule_website` свёл бы их в одну.
    "potok.io",
    "huntflow.io",
    "huntflow.ru",
    "amazingjobs.ru",
    "getmatch.ru",
    "jobs.ru",
    "talantix.ru",
    "rabota.ru",
    "trudvsem.ru",
    "career.ru",
    "greenhouse.io",
    "lever.co",
    # Общие хостинги ссылок, анкет и заметок: на таком хосте сидит кто угодно,
    # и одна ссылка на форму отклика склеила бы две разные компании.
    "docs.google.com",
    "forms.gle",
    "typeform.com",
    "telegra.ph",
    "notion.so",
    "taplink.cc",
    "bit.ly",
})


AGGREGATOR_BRANDS = frozenset({"indeed", "stepstone"})
"""Площадки вакансий, живущие выводком доменов: по домену на страну.

Перечислить их поимённо нельзя: у одной такой площадки доменов под шестьдесят,
и заводится новый без нашего ведома. Опознаются они не именем домена, а именем
площадки перед окончанием: `indeed.de`, `indeed.co.uk`, `de.indeed.com` — одна
и та же, а `indeed.acme.com` — чужой хост, который лишь начинается так же.
"""


def _is_brand_domain(host: str) -> bool:
    """Стоит ли за хостом площадка из `AGGREGATOR_BRANDS`.

    Имя площадки засчитывается, только если за ним не осталось ничего, кроме
    окончания домена. Окончание отличается длиной: `de`, `ru`, `com`, `co.uk`
    — не длиннее трёх букв каждое, а `acme` — длиннее. Правило грубое, но
    ошибается в безопасную сторону: незнакомое длинное окончание оставит хост
    обычным сайтом, то есть решать будет арбитр, а не склейка по домену.
    """
    labels = host.split(".")
    for i, label in enumerate(labels[:-1]):
        if label in AGGREGATOR_BRANDS:
            if all(len(rest) <= 3 for rest in labels[i + 1:]):
                return True
    return False


def is_aggregator_host(host: str) -> bool:
    """Правда ли, что за этим хостом не стоит одна компания.

    Сравнение по хвосту, а не по равенству: `careers.hh.ru` и `m.linkedin.com`
    — те же площадки, а `nothh.ru` — нет, поэтому хвост берётся с точкой.
    """
    if not host:
        return False
    for known in AGGREGATOR_HOSTS:
        if host == known or host.endswith("." + known):
            return True
    return _is_brand_domain(host)

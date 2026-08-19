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
    "telegra.ph",
    "notion.so",
    "taplink.cc",
    "bit.ly",
})


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
    return False

"""Заглавная буква в названии компании."""

from backend.domain.address_start import ADDRESS_START_RE


def capitalized_company_name(name: str | None) -> str | None:
    """Название компании, поднятое до заглавной буквы.

    Зовут отсюда трое — разбор поста, заведение карточки и её правка, — и
    правило у них одно: разойдись оно, компания получала бы заглавную букву при
    заведении и теряла её при первой же правке.

    Поднимается первая буква, а не первый знак: название пишут и в кавычках, и
    в скобках, и после номера («1с-битрикс»), и поднимай мы знак, такому
    названию не досталось бы ничего.

    Исключение одно: вторая буква заглавная при маленькой первой. Так бренды
    пишут себя сами («eBay», «iFly»), и поднятая первая буква сделала бы из
    имени другое.

    Считает исключение буквы, а не знаки: между первой и второй буквой стоит
    то цифра, то дефис — «x5 Retail», «i-Free», — и меряй мы соседний знак,
    оба поднялись бы вопреки правилу.

    Имя, начинающееся адресом, не поднимается вовсе. Такое имя оставляет
    разбор, когда в поле не нашлось ничего другого, и «Https://kontur.ru» —
    не название с заглавной буквы, а испорченный адрес.
    """
    if not name or ADDRESS_START_RE.match(name):
        return name
    first = next((at for at, letter in enumerate(name) if letter.isalpha()), None)
    if first is None:
        return name
    second = next((letter for letter in name[first + 1 :] if letter.isalpha()), "")
    if name[first].islower() and second.isupper():
        return name
    return name[:first] + name[first].upper() + name[first + 1 :]

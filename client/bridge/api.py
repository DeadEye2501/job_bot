"""Поверхность окна: домены, собранные в одно дерево.

Имя метода на странице — `api.<домен>.<метод>`, и собирает это дерево pywebview
сам, обходом полей. Отсюда и раскладка: домен — поле корня, а не примесь в один
плоский класс, как того требовал канал Qt с его единственным именем.

Доменов здесь сейчас четыре. Остальные пять переезжают слайсами А2.4–А2.9, и пока
переехали не все, рядом живёт `main_api.MainApi` со старой поверхностью.
"""

from __future__ import annotations

from client.bridge.blacklist import Blacklist
from client.bridge.hr import Hr
from client.bridge.hub import Hub
from client.bridge.stats import Stats
from client.bridge.vacancies import Vacancies


class Api:
    """Корень поверхности: держит домены, собранные из одного хозяйства."""

    def __init__(self, hub: Hub) -> None:
        self.blacklist = Blacklist(hub)
        self.hr = Hr(hub)
        self.stats = Stats(hub)
        self.vacancies = Vacancies(hub)

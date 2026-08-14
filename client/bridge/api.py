"""Поверхность окна: домены, собранные в одно дерево.

Имя метода на странице — `api.<домен>.<метод>`, и собирает это дерево pywebview
сам, обходом полей. Отсюда и раскладка: домен — поле корня, а не примесь в один
плоский класс, как того требовал канал Qt с его единственным именем.

Поверхность здесь одна и другой нет: обе формы окна — настроенное приложение и
первый запуск — ходят в эти же десять доменов.
"""

from __future__ import annotations

from client.bridge.blacklist import Blacklist
from client.bridge.channels import Channels
from client.bridge.companies import Companies
from client.bridge.hr import Hr
from client.bridge.hub import Hub
from client.bridge.profile import Profile
from client.bridge.settings import Settings
from client.bridge.system import System
from client.bridge.stats import Stats
from client.bridge.vacancies import Vacancies
from client.bridge.wizard import Wizard


class Api:
    """Корень поверхности: держит домены, собранные из одного хозяйства."""

    def __init__(self, hub: Hub) -> None:
        self.blacklist = Blacklist(hub)
        self.channels = Channels(hub)
        self.companies = Companies(hub)
        self.hr = Hr(hub)
        self.profile = Profile(hub)
        self.settings = Settings(hub)
        self.stats = Stats(hub)
        self.system = System(hub)
        self.vacancies = Vacancies(hub)
        self.wizard = Wizard(hub)

"""Следствия разбиения моста на примеси: что видит канал, а не питон.

Предмет здесь один — поверхность, которую `QWebChannel` публикует в окно. Все
остальные тесты зовут слоты питоном напрямую и подписываются на сигналы по
имени; этой дорогой поломка поверхности не видна вовсе, потому что питон
разрешает имя сам, мимо мета-объекта.
"""

from collections import Counter

from PySide6.QtCore import QObject, Signal

from client.bridge import MainApi, WizardApi


def _meta_entries(cls) -> list[str]:
    meta = cls.staticMetaObject
    return [
        meta.method(i).methodSignature().data().decode()
        for i in range(meta.methodCount())
    ]


def test_a_signal_declared_twice_really_lands_in_the_meta_object_twice():
    """Задвоенное объявление даёт две записи, а не одну.

    На этом и держится сторож ниже. Разбиение раскладывает сигналы по примесям,
    и забытая копия в наследнике не ошибка питона: `emit` возьмёт последнюю
    запись, а канал опубликует в окно первую — сигнал перестанет доходить.
    """

    class Mixin:
        done = Signal(str)

    class WithCopy(Mixin, QObject):
        done = Signal(str)

    entries = _meta_entries(WithCopy)
    assert Counter(entries)["done(QString)"] == 2


def test_the_window_gets_every_name_of_the_bridge_exactly_once():
    """Ни один слот и ни один сигнал не публикуется в окно дважды.

    Забытая при выносе копия объявления молча уводит сигнал мимо окна, и
    экран, который им живёт, замолкает целиком.
    """
    for surface in (MainApi, WizardApi):
        doubled = [
            name for name, times in Counter(_meta_entries(surface)).items()
            if times > 1
        ]
        assert doubled == [], surface.__name__

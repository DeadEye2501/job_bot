"""Обновление кэша курсов: раз в сутки, а без сети — прежний кэш."""

import logging
from datetime import datetime, timedelta

import httpx

from adapters import exchange_rates
from backend.repository.currency_rates import rates_fetched_at, save_rates
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)

# Источник сам обновляет курсы раз в сутки: чаще — те же числа и риск упереться
# в его предел частоты.
_FRESH_FOR = timedelta(days=1)
# После неудачи источник спрашивается снова не раньше чем через час: без сети
# запрос ждёт срок клиента, а «Прогнать заново» грузит слепки на каждую вакансию.
_RETRY_AFTER = timedelta(hours=1)


class RatesRefresh:
    """Обновление кэша курсов, помнящее свою последнюю неудачу."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory
        self._failed_at: datetime | None = None

    async def run(self) -> None:
        """Спросить источник, если кэшу больше суток.

        Запрос идёт вне сессии: SQLite не ждёт сети в открытой сделке. Беда сети
        или ответ не той формы оставляют прежний кэш — это и есть правило «без
        сети — последний кэш», а не заглушённая ошибка: кэш заполнен с миграции,
        и расчёт по нему верен, только курс старее. Ошибка записи в базу наверх
        уходит: перехват её не накрывает.
        """
        now = utc_now()
        if self._failed_at is not None and now - self._failed_at < _RETRY_AFTER:
            return
        async with self._session_factory() as session:
            fetched_at = await rates_fetched_at(session)
        if now - fetched_at < _FRESH_FOR:
            return
        try:
            rates = await exchange_rates.latest_rates()
        except (httpx.HTTPError, ValueError) as exc:
            self._failed(now, exc)
            return
        async with self._session_factory() as session:
            async with session.begin():
                saved = await save_rates(session, rates, now)
        if saved:
            self._failed_at = None
        else:
            self._failed(now, "в ответе нет ни одной нашей валюты")

    def _failed(self, now: datetime, why) -> None:
        self._failed_at = now
        logger.warning("курсы валют не обновлены, остаётся кэш: %s", why)

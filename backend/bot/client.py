"""Сборка бота: его состояние, соединения и поверхность, которой пользуется окно.

Работы здесь нет — она разошлась по соседям пакета, а класс держит их вместе и
даёт окну одно имя, к которому обращаться. Точка входа приложения лежит в корне
проекта: ``main.py``, он же связывает миграцию схемы, мастер и сборку бота.
"""

import asyncio
import logging
from typing import Literal

from pyrogram import filters
from pyrogram.handlers import (
    DeletedMessagesHandler,
    EditedMessageHandler,
    MessageHandler,
    RawUpdateHandler,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adapters import lm_studio, telegram
from backend.bot import rerun
from backend.bot import loop
from backend.bot import updates
from backend.bot import send
from backend.bot import chat
from backend.bot import channels
from backend.bot import slot
from backend.flows.pipeline import IngestionPipeline, LmProviders
from backend.models import BotMode
from backend.models import Message
from backend.runtime_settings import RuntimeSettings


logger = logging.getLogger(__name__)


def _open_connections(bot, runtime_settings: RuntimeSettings) -> None:
    """Соединения на весь срок жизни бота: Telegram и две модели."""
    # If construction fails partway through, any half-built httpx
    # clients will be closed by GC (with a ResourceWarning). We don't
    # try to clean them up here because httpx has no sync close() and
    # we can't await from sync __init__ — and init failure means the
    # process is about to exit anyway.
    bot.client = telegram.make_client(runtime_settings.tg)
    bot.lm_client = lm_studio.make_client(runtime_settings.chat)
    bot.lm_chat_model = runtime_settings.chat.model
    # Reuse the chat httpx client for embeddings if both providers point
    # at the same endpoint with the same auth.
    bot.lm_embed_client = (
        bot.lm_client
        if send._shares_provider(runtime_settings.chat, runtime_settings.embed)
        else lm_studio.make_client(runtime_settings.embed)
    )
    bot.lm_embed_model = runtime_settings.embed.model


def _subscribe_to_updates(bot) -> None:
    """Подписки на события Telegram: личные сообщения и сырые обновления."""
    bot.client.add_handler(
        MessageHandler(bot._on_dm, filters.private & filters.incoming)
    )
    bot.client.add_handler(
        MessageHandler(
            bot._on_dm_outgoing, filters.private & filters.outgoing
        )
    )
    bot.client.add_handler(
        EditedMessageHandler(bot._on_dm_edit, filters.private)
    )
    # NOTE: `filters.private` НЕ годится для DeletedMessagesHandler.
    # Pyrogram'овский parse_deleted_messages для UpdateDeleteMessages
    # (все приватные удаления) ставит msg.chat=None — peer info в этом
    # апдейте не приходит. filters.private требует m.chat.type in
    # {PRIVATE, BOT}, и для chat=None даёт False — handler не срабатывает
    # вообще. Поэтому пропускаем chatless-stub'ы и явные private-чаты,
    # отсекая каналы (UpdateDeleteChannelMessages приходит уже с
    # chat=Channel).
    bot.client.add_handler(
        DeletedMessagesHandler(
            bot._on_dm_delete,
            filters.private | filters.create(
                lambda _, __, m: getattr(m, "chat", None) is None
            ),
        )
    )
    # UpdateReadHistoryOutbox carries the «HR has read up to msg N» signal
    # for our outgoing DMs. Filter out everything else inside the handler;
    # raw updates fire for every server event.
    bot.client.add_handler(RawUpdateHandler(bot._on_raw_update))


def _declare_loop_controls(bot) -> None:
    """Рычаги, которыми окно правит уже запущенный цикл."""
    # Wake event = "skip the rest of the current sleep, poll now". Set
    # by kick(). Stop event = "shutdown after current iteration". Set
    # by stop().
    bot.wake_event = asyncio.Event()
    bot.stop_event = asyncio.Event()
    # Capture loop в run() — нужен для thread-safe kick / cancel /
    # request_stop из потока окна. Эти Event-ы и Task-и живут на
    # runner-loop'е; .set() / .cancel() из чужого треда — undefined
    # behavior (CPython его прощает, но контракт asyncio нарушается).
    bot.loop = None
    # Reference to the currently-running poll task so the UI's stop
    # button can cancel it without killing the whole bot loop.
    bot.current_poll_task = None


def _declare_ui_hooks(bot) -> None:
    """Места, куда окно вписывает свои отклики на события бота.

    Без окна все остаются пустыми, и бот работает молча. Их восемь: пять
    приходят от конвейера — их пересылает `_forward_pipeline_hooks`, — а три
    бот толкает сам: начало и конец оборота и отметку о прочтении.
    """
    # Optional UI hooks fired around each Full-mode poll cycle.
    bot.on_cycle_start = None  # filled in by client.bridge.lifespan under the UI
    bot.on_cycle_end = None     # filled in by client.bridge.lifespan under the UI
    # Forwarded from IngestionPipeline; the bridge puts this in its event queue.
    # Signature: on_progress(stage, label, current, total)
    bot.on_progress = None      # filled in by client.bridge.lifespan under the UI
    # Real-time chat push — fires after a new incoming HR DM is saved.
    # Signature: on_new_message(hr_id: int). The bridge puts it in the queue
    # the Contacts/HR pane reads.
    bot.on_new_message = None
    # Real-time HR-read-receipt push. Signature:
    # on_hr_read(hr_id: int, max_tg_id: int). Cheaper than on_new_message
    # because the UI only needs to flip ✓ → ✓✓ on already-rendered rows
    # rather than refetch the whole chat.
    bot.on_hr_read = None
    # Real-time push for the Contacts/Channels pane: fires once per poll
    # cycle, right after the title sweep writes any new titles into the
    # DB. UI re-fetches the list so the user sees fresh names without
    # having to switch tabs or restart.
    bot.on_channels_changed = None
    # Real-time push for Contacts/HR + Contacts/Companies: fires after
    # каждой commit'а с парсингом вакансии, который мог через
    # find_or_create_* создать/обновить HR/Company. Дёргается во время
    # длинных циклов (90 минут на 18 каналов), а не только по
    # завершении ingestion_finished.
    bot.on_contacts_changed = None
    # Real-time push для вкладки «Вакансии». Заменяет 5-сек JS-таймер:
    # каждый раз когда в БД меняется Vacancy — фронт сразу делает
    # refetch.
    bot.on_vacancies_changed = None


def _forward_pipeline_hooks(bot) -> None:
    """Отклики конвейера пересылаются наружу — тому, кто вписан в бота."""
    bot.ingestion.on_progress = lambda stage, label, cur, tot: (
        bot.on_progress and bot.on_progress(stage, label, cur, tot)
    )
    bot.ingestion.on_channels_changed = lambda: (
        bot.on_channels_changed and bot.on_channels_changed()
    )
    bot.ingestion.on_contacts_changed = lambda: (
        bot.on_contacts_changed and bot.on_contacts_changed()
    )
    bot.ingestion.on_vacancies_changed = lambda: (
        bot.on_vacancies_changed and bot.on_vacancies_changed()
    )
    bot.ingestion.on_new_message = lambda hr_id: (
        bot.on_new_message and bot.on_new_message(hr_id)
    )


class Bot:
    """Бот целиком: соединение, режим, цикл и его сотрудники.

    Поля, которыми пользуются соседи по пакету — клиент Telegram, фабрика
    сессий, настройки, конвейер, — открытые. Подчёркивание оставлено ровно
    тем, что дальше этого файла не ходит: ссылкам на обработчики, которые
    здесь же и вешаются на клиента. Прежде закрытыми числились и общие, и
    обещание «дальше модуля не идёт» было неправдой почти двести раз.
    """

    # Оба поля ставит `_declare_loop_controls`, а объявлены они здесь:
    # присвоение по чужому полю (`bot.loop = ...`) тип не записывает,
    # и без этих двух строк класс не объявляет ни одного своего поля.
    loop: asyncio.AbstractEventLoop | None
    current_poll_task: asyncio.Task | None

    def __init__(
        self,
        runtime_settings: RuntimeSettings,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        dry_run: bool = False,
    ) -> None:
        self.dry_run = dry_run
        if runtime_settings.tg is None:
            raise RuntimeError("Bot: TG account not configured")
        if runtime_settings.chat is None:
            raise RuntimeError("Bot: chat LLM not configured")
        if runtime_settings.embed is None:
            raise RuntimeError("Bot: embedding LLM not configured")

        self.rs = runtime_settings
        self.session_factory = session_factory
        _open_connections(self, runtime_settings)
        self.ingestion = IngestionPipeline(
            client=self.client,
            session_factory=self.session_factory,
            models=LmProviders(
                chat_client=self.lm_client,
                chat_model=self.lm_chat_model,
                embed_client=self.lm_embed_client,
                embed_model=self.lm_embed_model,
            ),
            send=self.send,
            runtime_settings=self.rs,
        )
        _subscribe_to_updates(self)
        _declare_loop_controls(self)
        _declare_ui_hooks(self)
        _forward_pipeline_hooks(self)

    @property
    def is_ready(self) -> bool:
        """True after Bot.run() прошёл await client.start() и захватил loop.

        До этой точки Pyrogram-клиент ещё не подключён. Спрашивает его лампочка
        связи — через `is_connected` рядом, — и больше никто: у остальных дорог
        свой заслон, отвечающий окну словом, а не молчанием."""
        return self.loop is not None

    @property
    def is_connected(self) -> bool:
        """Держится ли сейчас связь с Telegram.

        Отдельно от `is_ready`: тот говорит, что бот запустился, а этот — что
        сессия жива прямо сейчас. Отваливается он не мгновенно: биение
        Pyrogram ловит обрыв за полминуты-минуту.

        Объявлено здесь, потому что спрашивает лампочка окна, а лазить в
        закрытый `_client` снаружи ей нечем — и прежде она делала именно это.
        """
        return bool(
            self.is_ready and getattr(self.client, "is_connected", False)
        )

    def kick(self) -> None:
        """Wake the loop so the next poll runs immediately instead of waiting.

        Зовётся из потока окна — почему через `slot.on_runner_loop`, сказано
        там же.
        """
        logger.debug("Poll wake requested")
        slot.on_runner_loop(self, self.wake_event.set)


    def request_stop(self) -> None:
        """Ask the loop to exit after the current iteration.

        Thread-safe: см. ``kick``.
        """
        logger.info("Stop requested")
        slot.on_runner_loop(self, self.stop_event.set)
        slot.on_runner_loop(self, self.wake_event.set)


    async def poll_channel_now(
        self, channel_id
    ) -> Literal["ok", "busy", "missing", "blacklisted", "cancelled", "error"]:
        return await channels.poll_channel_now(self, channel_id)

    async def delete_channel(self, channel_id) -> int | None:
        return await channels.delete_channel(self, channel_id)

    async def add_channel(self, username) -> tuple[int | None, Literal["created", "exists", "invalid"]]:
        return await channels.add_channel(self, username)

    def cancel_current_poll(self) -> None:
        return slot.cancel_current_poll(self)

    async def force_poll_once(self) -> Literal["ok", "busy", "cancelled", "error"]:
        return await channels.force_poll_once(self)

    async def mark_hr_chat_read(self, hr_id) -> int:
        return await chat.mark_hr_chat_read(self, hr_id)

    async def send_to_hr_chat(self, hr_id, text) -> Message:
        return await chat.send_to_hr_chat(self, hr_id, text)

    async def send_to_hr_media(self, hr_id, file_path) -> Message:
        return await chat.send_to_hr_media(self, hr_id, file_path)

    async def ui_send_vacancy_application(self, vacancy_id) -> tuple[bool, str]:
        return await send.ui_send_vacancy_application(self, vacancy_id)

    async def send(self, hr, text, attachment=None, vacancy_id=None, *, force=False) -> bool:
        return await send.send(self, hr, text, attachment, vacancy_id, force=force)

    async def _on_raw_update(self, _client, update, _users, _chats) -> None:
        return await updates.on_raw_update(self, _client, update, _users, _chats)

    async def _on_dm_edit(self, _client, msg) -> None:
        return await updates.on_dm_edit(self, _client, msg)

    async def _on_dm_delete(self, _client, messages) -> None:
        return await updates.on_dm_delete(self, _client, messages)

    async def _on_dm_outgoing(self, _client, msg) -> None:
        return await updates.on_dm_outgoing(self, _client, msg)

    async def _on_dm(self, _client, msg) -> None:
        return await updates.on_dm(self, _client, msg)

    async def log_out_session(self) -> None:
        return await loop.log_out_session(self)

    async def current_mode(self) -> BotMode:
        return await loop.current_mode(self)

    async def run(self, *, once=False) -> None:
        return await loop.run(self, once=once)

    async def ui_rerun_vacancy_pipeline(
        self, vacancy_id
    ) -> Literal["ok", "busy", "missing", "no_text", "llm", "cancelled", "error"]:
        return await rerun.ui_rerun_vacancy_pipeline(self, vacancy_id)

    async def ui_forget_vacancy(self, vacancy_id) -> bool:
        return await self.ingestion.forget_vacancy(vacancy_id)

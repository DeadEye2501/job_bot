"""Сборка конвейера: его состояние, общие ресурсы и поверхность для зовущих.

Работы здесь нет — она разошлась по соседям пакета, а класс держит их вместе:
владеет соединениями, кэшами анкеты и чёрного списка, оповещениями окна и даёт
одно имя, к которому обращаются бот и мост.
"""

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Literal
from pathlib import Path

from backend.domain.dedup import EmbeddingCache
from backend.flows.dm import DmHelpers
from backend.flows.dm_backfill import DmHooks
from backend.flows.dm_debounce import DmDebounce
from backend.notify import fire

from backend.flows import apply
from backend.flows import dm_classify
from backend.flows import channels
from backend.flows import rerun
from backend.flows import cleanup
from backend.flows import ghosting
from backend.llm import candidate
from backend.llm.candidate import CandidateProfile
from backend.models import ProfileSkill
from backend.repository.blacklist_marks import load_active_blacklist_patterns
from backend.repository.profile import get_profile, list_profile_languages, list_skills
from backend.repository.profile_block import build_profile_block


logger = logging.getLogger(__name__)







def _declare_caches(pipeline) -> None:
    """Слепки, которые конвейер держит при себе, — и у них два хозяина.

    Анкету и чёрный список перестраивает `reload_resources` разом; до
    первой загрузки они пусты, и валидатор подставит «—» во все слоты, что
    равносильно «нет ограничений». Кэш векторов живёт своей жизнью
    (`domain/dedup.EmbeddingCache`): `reload_resources` его не трогает вовсе,
    он наполняется по требованию и сам помнит, наполнялся ли.
    """
    # Текстовый блок «Информация о кандидате» для cover-letter prompt'а.
    pipeline.profile_block = ""
    pipeline.embeddings = EmbeddingCache()
    pipeline.skills_cache = []
    # Срез данных профиля для LLM-валидатора.
    pipeline.profile_cache = CandidateProfile()
    pipeline.blacklist_patterns = []


def _declare_window_hooks(pipeline) -> None:
    """Отклики, которые конвейер толкает по ходу работы.

    Заполняет их бот своими — теми же именами, но своими полями, — и
    делает это отдельным объявлением. Конвейер про бота не знает нарочно:
    знал бы — завёлся бы круг ввозов.
    """
    # Optional UI hook: called as on_progress(stage, label, current, total).
    # stage: "channel" — across channels in poll_active_channels;
    #        "message" — across messages inside the current channel.
    # Semantics: current = "how many already done", so it ranges 0..total.
    pipeline.on_progress = None
    # Толкается без доводов после каждой удавшейся записи сводки каналов —
    # названий, картинок или того и другого сразу. Зовут сводку двое: обход
    # перед чтением постов и заведение канала из окна, — и обоим нужно одно:
    # список каналов в окне обновляется сам, без перехода по вкладкам.
    pipeline.on_channels_changed = None
    # Optional UI hook: called with no args after a vacancy parse commit
    # that may have created/updated HR or Company rows (via
    # find_or_create_*). Drives real-time refresh of Contacts/HR and
    # Contacts/Companies lists during long poll cycles — а не только по
    # завершении ingestion_finished.
    pipeline.on_contacts_changed = None
    # Optional UI hook: called with no args after любого commit'а,
    # который меняет состояние Vacancy (новая распарсенная вакансия,
    # delete, или DM-classifier изменил статус). Drives real-time
    # refresh вкладки «Вакансии» — push-аналог 5-сек polling-таймера,
    # который раньше был на JS-стороне.
    pipeline.on_vacancies_changed = None
    # Optional UI hook: called as on_new_message(hr_id) после persist'а
    # сообщения (в т.ч. backfill'ом нового HR'а из автоаплая).
    pipeline.on_new_message = None


def _declare_dm_debounce(pipeline) -> None:
    """Копилка и таймеры пачки писем от одного HR.

    Юзеры (особенно русскоязычные) часто пишут одну мысль 3-5 короткими
    сообщениями подряд. Классификация каждой по отдельности → лишние
    LLM-вызовы и шанс что верно классифицируется только одно (часто
    последнее, но не всегда). Накапливаем 60 сек после последнего сообщения
    от HR, потом одна классификация на склеенный текст, а вердикт по ней
    прикладывается к вакансии и письму **последнего** в пачке.
    """
    # Предел пачки на одного человека — защита от спама: пятьдесят сообщений в
    # одном окне ожидания уже точно ненормально, а тысячи строк раздувают
    # память и не дают ничего — модель всё равно отрежет хвост.
    #
    # Разрешений обратиться к модели два. Переход из OFF в рабочий режим может
    # разом разбудить таймеры по всем людям, что на локальной LM Studio
    # превращается в тридцать одновременных обращений к одному серверу — она
    # ставит их в очередь, начинает таймаутить, и часть вердиктов теряется.
    pipeline.dm_debounce = DmDebounce(cap=50, slots=2)


@dataclass(frozen=True, slots=True)
class LmProviders:
    """Оба соединения с моделями и оба имени моделей — одной группой.

    Ходят они только вместе: чат-модель разбирает объявление и выносит
    вердикт, модель отпечатков считает векторы, и лежать эти двое могут на
    разных серверах. Порознь доводами они дают восемь доводов у сборки
    конвейера — и путаются местами при сборке, потому что тип у обоих
    соединений один.
    """

    chat_client: object
    chat_model: str
    embed_client: object
    embed_model: str


class IngestionPipeline:
    """Конвейер: сотрудники, кэши и работа над вакансией от поста до отклика.

    Поля открытые, и это не небрежность: ими пользуются одиннадцать соседних
    модулей пакета — читают настройки, берут фабрику сессий, правят кэш
    отпечатков и копилку отложенного разбора. Прежде они числились закрытыми,
    и подчёркивание обещало то, чего не было.

    Кэш отпечатков и копилка отложенного разбора полями здесь больше не
    лежат: у обоих свои объекты со своими правилами
    (`domain/dedup.EmbeddingCache`, `flows/dm_debounce.DmDebounce`), и
    договор внутри каждого снаружи уже не разорвать.
    """

    # Поля ставят объявления выше, а объявлены они здесь: присвоение по
    # чужому полю (`pipeline.skills_cache = ...`) тип не записывает.
    profile_block: str
    skills_cache: list[ProfileSkill]
    profile_cache: CandidateProfile
    blacklist_patterns: list[str]
    dm_debounce: DmDebounce

    def __init__(
        self,
        client,
        session_factory,
        models: LmProviders,
        send,
        runtime_settings,
    ) -> None:
        self.client = client
        self.session_factory = session_factory
        self.lm_client = models.chat_client
        self.lm_embed_client = models.embed_client
        self.lm_chat_model = models.chat_model
        self.lm_embed_model = models.embed_model
        self.send = send
        self.rs = runtime_settings
        _declare_caches(self)
        _declare_window_hooks(self)
        _declare_dm_debounce(self)

        # Strong-references на in-flight per-HR backfill таски (kicked
        # из flows/dm.py, spawn_hr_backfill). Event loop держит на тасках только
        # weak-ref'ы — без своего set'а Python может GC'нуть таск
        # посреди выполнения с warning'ом «Task was destroyed but it
        # is pending». На done-callback'е сам себя убираем из set'а.
        self.backfill_tasks: set[asyncio.Task] = set()

        # Отметка «гасимся». Ставится в `Bot.run` до `client.stop()` и
        # закрытия соединений с моделями; читает её отложенный разбор писем
        # (`dm_classify`) и молча ничего не делает — чтобы обработчик
        # Pyrogram, отстреливший уже после гашения, не полез в закрытое
        # соединение. Сама запись входящего письма отметки не читает: письмо,
        # дошедшее до нас, ложится в базу при любом исходе.
        self.shutting_down: bool = False

    def mark_shutting_down(self) -> None:
        """Bot.run finally: с этого момента DM-handler ничего не делает."""
        self.shutting_down = True
        for task in self.backfill_tasks:
            task.cancel()


    DM_CLASSIFY_DEBOUNCE_SEC = 60.0
    # Сколько остановка ждёт начавшийся разбор. Названа отдельно, потому что
    # на выключении по её истечении разбор всё-таки гасят, и проверить это,
    # не просидев пять секунд, иначе нечем.
    DM_CLASSIFY_STOP_TIMEOUT_SEC = 5.0


    def emit_progress(self, stage: str, label: str, current: int, total: int) -> None:
        fire(self.on_progress, "on_progress", stage, label, current, total)

    def fire_contacts_changed(self) -> None:
        fire(self.on_contacts_changed, "on_contacts_changed")

    def fire_vacancies_changed(self) -> None:
        fire(self.on_vacancies_changed, "on_vacancies_changed")


    async def reload_resources(self) -> None:
        # Кэши skills/blacklist/profile/languages/profile_block обновляются
        # ровно один раз — в начале каждого poll-цикла. Если юзер редактирует
        # профиль через UI между циклами, изменения подхватятся ТОЛЬКО на
        # следующем `poll_active_changes`. Это намеренно: cache invalidation
        # из UI-bridge'а потребует cross-thread hook'а, и польза маргинальная
        # (юзер редко редактирует профиль во время активного полла).
        async with self.session_factory() as session:
            self.skills_cache = await list_skills(session)
            self.blacklist_patterns = await load_active_blacklist_patterns(
                session
            )
            profile = await get_profile(session)
            languages = await list_profile_languages(session)
            self.profile_cache = replace(
                candidate.build_candidate_profile(profile, languages),
                known_skills=self.skills_cache,
            )
            self.profile_block = await build_profile_block(session)
        logger.info(
            "loaded resources: %d skills, %d blacklist patterns, "
            "profile_title=%r, %d languages, profile_block=%d chars",
            len(self.skills_cache),
            len(self.blacklist_patterns),
            self.profile_cache.title,
            len(self.profile_cache.languages),
            len(self.profile_block),
        )

    def cv_path(self):
        """Путь к резюме из настроек; пусто — путь не задан.

        Лежит ли по нему файл, здесь не спрашивают: настройку правит человек,
        а между вопросом и отправкой файл всё равно успевает исчезнуть. Пустое
        место разбирает тот, кто прикладывает резюме к письму.
        """
        raw = self.rs.cv_path
        if not raw:
            return None
        return Path(raw)


    async def check_ghosting_timeouts(self) -> int:
        return await ghosting.check_ghosting_timeouts(self)

    async def rerun_pipeline_for_vacancy(
        self, vacancy_id
    ) -> Literal["ok", "missing", "no_text", "llm"]:
        return await rerun.rerun_pipeline_for_vacancy(self, vacancy_id)

    async def recover_orphan_vacancies(self) -> int:
        return await rerun.recover_orphan_vacancies(self)

    async def poll_active_channels(self) -> None:
        return await channels.poll_active_channels(self)

    async def forget_vacancy(self, vacancy_id) -> bool:
        return await cleanup.forget_vacancy(self, vacancy_id)

    async def poll_one_channel(
        self, channel_id
    ) -> Literal["ok", "missing", "blacklisted", "error"]:
        return await channels.poll_one_channel(self, channel_id)

    async def refresh_channel_metadata_for_ids(self, channel_ids) -> None:
        return await channels.refresh_channel_metadata_for_ids(self, channel_ids)

    def update_dm_buffer_text(self, hr_id, tg_msg_id, new_text) -> None:
        """HR поправил письмо, ещё ждущее разбора, — разбор увидит свежее."""
        return self.dm_debounce.retext(hr_id, tg_msg_id, new_text or "")

    def remove_dm_buffer_msg(self, hr_id, tg_msg_id) -> None:
        """HR удалил письмо, ещё ждущее разбора, — в пачку оно не пойдёт."""
        return self.dm_debounce.forget(hr_id, tg_msg_id)

    def schedule_dm_classification(self, hr_id, reply) -> None:
        return dm_classify.schedule_dm_classification(self, hr_id, reply)

    def dm_helpers(self) -> DmHelpers:
        """Сотрудники для проводки письма — одним местом сборки.

        Собирают их трое: приём живого письма, догон при переходе в рабочий
        режим и догон свежего собеседника. Набор один и тот же, и знание, из
        чего он складывается, разъезжалось по трём слоям — добавленное поле
        приходилось вписывать в каждый.
        """
        return DmHelpers(
            session_factory=self.session_factory,
            lm_client=self.lm_client,
            lm_chat_model=self.lm_chat_model,
            client=self.client,
            schedule_classification=self.schedule_dm_classification,
        )

    def dm_hooks(self) -> DmHooks:
        """Чем догон будит окно — оттуда же, откуда и сотрудники."""
        return DmHooks(
            on_message_persisted=self.on_new_message,
            on_vacancies_changed=self.on_vacancies_changed,
        )

    async def cancel_pending_dm_classifications(self, *, drain=False) -> None:
        return await dm_classify.cancel_pending_dm_classifications(self, drain=drain)

    async def send_application_for_vacancy(self, vacancy_id) -> tuple[bool, str]:
        return await apply.send_application_for_vacancy(self, vacancy_id)

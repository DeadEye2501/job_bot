import asyncio
import logging
from pathlib import Path

import numpy as np

from backend.flows import apply
from backend.flows import dm_classify
from backend.flows import channels
from backend.flows import rerun
from backend.flows import cleanup
from backend.llm.candidate import CandidateProfile
from backend.models import (
    ProfileSkill,
)
from backend.repository.blacklist import load_active_blacklist_patterns
from backend.repository.profile import build_profile_block, get_profile, list_profile_languages, load_profile_skills


logger = logging.getLogger(__name__)










class IngestionPipeline:
    def __init__(
        self,
        client,
        session_factory,
        lm_client,
        lm_embed_client,
        lm_chat_model: str,
        lm_embed_model: str,
        send,
        runtime_settings,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._lm_client = lm_client
        self._lm_embed_client = lm_embed_client
        self._lm_chat_model = lm_chat_model
        self._lm_embed_model = lm_embed_model
        self._send = send
        self._rs = runtime_settings
        # Текстовый блок «Информация о кандидате» для cover-letter prompt'а.
        # Перестраивается в _reload_resources рядом с skills/blacklist.
        self._profile_block: str = ""
        self._embedding_ids: np.ndarray = np.empty((0,), dtype=np.int64)
        self._embedding_matrix: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self._embedding_cache_loaded = False
        self._skills_cache: list[ProfileSkill] = []
        # Срез данных профиля для LLM-валидатора. Перестраивается в
        # _reload_resources вместе со skills/blacklist. До первой загрузки —
        # пустой профиль, валидатор подставит "—" во все слоты (равносильно
        # «нет ограничений»).
        self._profile_cache: CandidateProfile = CandidateProfile()
        self._blacklist_patterns: list[str] = []
        # Optional UI hook: called as on_progress(stage, label, current, total).
        # stage: "channel" — across channels in poll_active_channels;
        #        "message" — across messages inside the current channel.
        # Semantics: current = "how many already done", so it ranges 0..total.
        self.on_progress = None  # filled in by Bot.__init__ if running under the UI
        # Optional UI hook: called with no args after the title sweep at the
        # start of a poll cycle has written one or more title changes. Lets
        # the Contacts/Channels pane auto-refresh in real time without the
        # user having to switch tabs or restart the app.
        self.on_channels_changed = None
        # Optional UI hook: called with no args after a vacancy parse commit
        # that may have created/updated HR or Company rows (via
        # find_or_create_*). Drives real-time refresh of Contacts/HR and
        # Contacts/Companies lists during long poll cycles — а не только по
        # завершении ingestion_finished.
        self.on_contacts_changed = None
        # Optional UI hook: called with no args after любого commit'а,
        # который меняет состояние Vacancy (новая распарсенная вакансия,
        # delete, или DM-classifier изменил статус). Drives real-time
        # refresh вкладки «Вакансии» — push-аналог 5-сек polling-таймера,
        # который раньше был на JS-стороне.
        self.on_vacancies_changed = None
        # Optional UI hook: called as on_new_message(hr_id) после persist'а
        # сообщения (в т.ч. backfill'ом нового HR'а из автоаплая). Bot
        # форвардит сюда свой self.on_new_message, чтобы IngestionPipeline
        # мог толкать chat-update без обратной зависимости на Bot.
        self.on_new_message = None

        # === DM burst-debounce =========================================
        # Юзеры (особенно русскоязычные) часто пишут одну мысль 3-5
        # короткими сообщениями подряд. Классификация каждой по отдельности
        # → лишние LLM-вызовы и шанс что верно классифицируется только
        # одно (часто последнее, но не всегда). Накапливаем 60 сек после
        # последнего сообщения от HR, потом одна классификация на склеенный
        # текст. Apply применяется к vacancy_id и msg_id ПОСЛЕДНЕГО
        # сообщения в burst'е.
        self._dm_classify_buffer: dict[int, list[dict]] = {}
        self._dm_classify_tasks: dict[int, asyncio.Task] = {}
        # Семафор на одновременные LLM-классификации. Catch-up на OFF→active
        # transition'е может разом разбудить debounce'ры по всем HR'ам, что
        # на локальной LM Studio превращается в 30 параллельных httpx.post
        # к одному серверу — она ставит их в очередь, начинает таймаутить и
        # часть вердиктов теряется. 2 одновременных вызова — компромисс
        # между throughput'ом и не-OOM'нуть LM Studio.
        self._dm_classify_semaphore = asyncio.Semaphore(2)

        # Strong-references на in-flight per-HR backfill таски (kicked
        # из _spawn_hr_backfill). Event loop держит на тасках только
        # weak-ref'ы — без своего set'а Python может GC'нуть таск
        # посреди выполнения с warning'ом «Task was destroyed but it
        # is pending». На done-callback'е сам себя убираем из set'а.
        self._backfill_tasks: set[asyncio.Task] = set()

        # Shutdown-флаг. Bot.run finally выставляет его в True ДО
        # client.stop() / lm_*.aclose() — после этого schedule_dm_class*
        # и process_dm молча no-op'ят, чтобы Pyrogram'овский handler,
        # успевший отстрелить уже после teardown'а, не насыпал в БД
        # запись и не попытался дёрнуть закрытый httpx-клиент.
        self._shutting_down: bool = False

    def mark_shutting_down(self) -> None:
        """Bot.run finally: с этого момента DM-handler ничего не делает."""
        self._shutting_down = True
        for task in self._backfill_tasks:
            task.cancel()


    DM_CLASSIFY_DEBOUNCE_SEC = 60.0
    # Cap buffer'а на одного HR — защита от спама. 50 сообщений в одном
    # debounce-окне (60с) уже точно ненормально; накопление тысяч строк
    # раздувает память и rам прибавляет ничего полезного — LLM всё равно
    # отрежет хвост в classify_hr_reply.
    DM_CLASSIFY_BUFFER_CAP = 50


    def _emit_progress(self, stage: str, label: str, current: int, total: int) -> None:
        if self.on_progress is None:
            return
        try:
            self.on_progress(stage, label, current, total)
        except Exception:
            logger.exception("on_progress hook failed")


    def _fire_contacts_changed(self) -> None:
        if self.on_contacts_changed is None:
            return
        try:
            self.on_contacts_changed()
        except Exception:
            logger.exception("on_contacts_changed hook failed")

    def _fire_vacancies_changed(self) -> None:
        if self.on_vacancies_changed is None:
            return
        try:
            self.on_vacancies_changed()
        except Exception:
            logger.exception("on_vacancies_changed hook failed")


    async def _reload_resources(self) -> None:
        # Кэши skills/blacklist/profile/languages/profile_block обновляются
        # ровно один раз — в начале каждого poll-цикла. Если юзер редактирует
        # профиль через UI между циклами, изменения подхватятся ТОЛЬКО на
        # следующем `poll_active_changes`. Это намеренно: cache invalidation
        # из UI-bridge'а потребует cross-thread hook'а, и польза маргинальная
        # (юзер редко редактирует профиль во время активного полла).
        async with self._session_factory() as session:
            self._skills_cache = await load_profile_skills(session)
            self._blacklist_patterns = await load_active_blacklist_patterns(
                session
            )
            profile = await get_profile(session)
            languages = await list_profile_languages(session)
            self._profile_cache = apply._build_candidate_profile(profile, languages)
            self._profile_block = await build_profile_block(session)
        logger.info(
            "loaded resources: %d skills, %d blacklist patterns, "
            "profile_title=%r, %d languages, profile_block=%d chars",
            len(self._skills_cache),
            len(self._blacklist_patterns),
            self._profile_cache.title,
            len(self._profile_cache.languages),
            len(self._profile_block),
        )

    def _cv_path(self):
        """Path к резюме (PDF), если задан в настройках. None если не задан
        или файл не существует — caller должен skip'нуть отправку."""
        raw = self._rs.cv_path
        if not raw:
            return None
        return Path(raw)


    async def check_ghosting_timeouts(self):
        return await cleanup.check_ghosting_timeouts(self)

    async def rerun_pipeline_for_vacancy(self, vacancy_id):
        return await rerun.rerun_pipeline_for_vacancy(self, vacancy_id)

    async def recover_orphan_vacancies(self):
        return await rerun.recover_orphan_vacancies(self)

    async def poll_active_channels(self):
        return await channels.poll_active_channels(self)

    async def poll_one_channel(self, channel_id):
        return await channels.poll_one_channel(self, channel_id)

    async def refresh_channel_metadata_for_ids(self, channel_ids):
        return await channels.refresh_channel_metadata_for_ids(self, channel_ids)

    def update_dm_buffer_text(self, hr_id, msg_id, new_text):
        return dm_classify.update_dm_buffer_text(self, hr_id, msg_id, new_text)

    def remove_dm_buffer_msg(self, hr_id, msg_id):
        return dm_classify.remove_dm_buffer_msg(self, hr_id, msg_id)

    def schedule_dm_classification(self, hr_id, vacancy_id, msg_id, text):
        return dm_classify.schedule_dm_classification(self, hr_id, vacancy_id, msg_id, text)

    async def cancel_pending_dm_classifications(self, *, drain=False):
        return await dm_classify.cancel_pending_dm_classifications(self, drain=drain)

    async def send_application_for_vacancy(self, vacancy_id):
        return await apply.send_application_for_vacancy(self, vacancy_id)

# Итоговое ревью: повторы по картам, весь Python-проект (HEAD 251040f)

Источник: `docs/maps/module-map.md` (6878 строк) и `docs/maps/data-map.md` (2230 строк)
прочитаны целиком. `docs/not-duplicates.md` в дереве нет, поэтому пропускать было нечего.

Проходов было два. В первом обе карты прочитаны подряд: карта модулей семью кусками,
карта данных тремя. По ходу выписан список кандидатов (около 45). Во втором проходе
каждый кандидат сверен по коду, обе стороны читались глазами. В отчёт попало только
подтверждённое чтением. Свежесть установлена через `git blame` и
`git log 174c0ca..251040f`.

### Strengths

- Свежий код этапа почти везде берёт готовое, а не пишет своё. `slot.slot_taken`
  остался единственным местом, где читается `current_poll_task`: grep по
  `backend/` и `client/` других чтений не находит. `HumanGate.reveal` выводит
  браузер вперёд через собственный `_show`. `client/bridge/media._image_type`
  стоит на `backend/bot/media.image_type`, и таблица подписей одна.
  `client/bridge/vacancies.screening` читает `applications.vacancy_screening`.
  `client/bridge/mail.py` берёт `known_server` и `MailSettings` из репозитория и
  ничего своего не держит.
- Близнецы прежних этапов уже сведены, и решение записано рядом с кодом:
  - три вопроса о пригодности — тонкие обёртки над `fit.ask_fit`;
  - выключение по отметке у каналов и агрегаторов — `BlacklistMark.switch_off`;
  - две анкеты (`profile_block`, `agent_profile`) делят `domain/tenure`;
  - `ingest.save_new_vacancy` и `pasted` ведут в `intake.save_new_vacancy`;
  - `site_home` и `telegraph` строят клиент через `web_page.page_client`;
  - `fit_preferences` и `fit_role` — разные наставления над общим
    `ask_fit`/`FitQuestion`;
  - `read_llm_creds` — одно правило на пробу связи и на запись обоих поставщиков.
- Где пары разошлись намеренно, расхождение объяснено в докстроке или комментарии,
  со ссылкой на решение человека. Так оформлены порядки статусов (19.08), засов
  жалобы журнала, `str_or_none` против `text_or_none`, `_spelled_in` против
  `spelled_alone`, проба модели в `health` против проверки из моста.

### Issues

#### Critical (Must Fix)

Нет.

#### Important (Should Fix)

1. **Порт STARTTLS объявлен дважды.**
   - Где: `adapters/smtp_mail.py:14` и `backend/repository/mail_account.py:13`.
     В обоих файлах `_STARTTLS_PORT = 587`. Копия в репозитории пришла в свежем
     коммите 251040f.
   - Что повторено: одно знание — «на 587 сервер ждёт STARTTLS». Адаптер по этому
     числу выбирает `SMTP` + `starttls` вместо `SMTP_SSL`. Репозиторий подставляет
     его Outlook-у в `_KNOWN_SERVERS`, рассчитывая именно на эту ветку адаптера.
   - Чем отличаются: пока ничем.
   - Чем опасно: правка одной стороны молча ломает подставленный сервер. Тогда
     подключение уходит в `SMTP_SSL` на 587, и письмо не уходит.
   - Что оставить: объявление в `adapters/smtp_mail.py`, сделав его публичным
     (`STARTTLS_PORT`). `mail_account.py` уже импортирует оттуда
     `MailAccountConfig` и должен импортировать порт тем же путём, а свою копию
     удалить.

#### Minor (Nice to Have)

2. **Две читалки одной строки почты в одном модуле.**
   - Где: `backend/repository/mail_account.py:37-52` (`get_mail_account`) и
     `:55-68` (`read_mail_account`, свежая, 251040f).
   - Что повторено: обе читают `MailAccount` id=1, расшифровывают пароль вызовом
     `decrypt_or_none(..., "mail password")` и зовут `remember_secret`.
     Расшифровка с запоминанием написана дважды.
   - Чем отличаются: только контрактом выхода. Одна отдаёт готовое к отправке или
     пусто, другая — «как записано».
   - Что оставить: `read_mail_account`. `get_mail_account` строится поверх неё:
     если нет адреса, пароля, хоста или порта, вернуть пусто, иначе
     `MailAccountConfig(...)`.
   - Рядом, без претензии: `MailSettings` и `MailAccountConfig` имеют те же четыре
     поля. Это два состояния (черновик и готовое), поэтому пара отложена — см.
     раздел «Declined to judge».

3. **Контакты вакансии читаются своим запросом рядом с готовым.**
   - Где: `backend/repository/aggregators.py:114-116` (`vacancy_barred_host`,
     свежий, 1a921a5) делает
     `select(VacancyContact.value).where(VacancyContact.vacancy_id == ...)`. Готовое
     — `backend/repository/vacancy_contacts.py:69-75` (`list_contacts`).
     `aggregator_apply.vacancy_ways` для того же вопроса зовёт именно
     `list_contacts`.
   - Чем опасно: появись у контактов отбор (например, удалённые), отсев сайта и
     выбор способа разойдутся молча.
   - Что оставить: `list_contacts`. `vacancy_barred_host` берёт
     `[c.value for c in await list_contacts(...)]`.

4. **Подсказка доступности агента вкладывается в таблицу отказов в двух местах.**
   - Где: `client/bridge/aggregators.py:170` и `client/bridge/vacancy_actions.py:100`.
     В обоих стоит `{**ТАБЛИЦА, "locked": current_refusal(self._hub.rs.chat) or ""}`.
     Коммиты b26480a и 85638f0, до базы.
   - Что повторено: правило «исход `locked` объясняется текущей подсказкой
     доступности». Его описание лежит в `refusals.py`, у `APPLY_VIA_REFUSALS`.
   - Что оставить: один помощник рядом с таблицами, например
     `agent_refusals(table, chat)` в `client/bridge/refusals.py` или в
     `client/bridge/aggregators.py`. Оба места зовут его.

5. **Строка-маркер «готово» написана трижды и сравнивается.**
   - Где: `backend/agent/human_gate.py:65`, `:112`, `:113`. Значение записывается,
     возвращается и сравнивается через `answer == "готово"`.
   - Чем опасно: это маркер, а не фраза. Опечатка в одном месте ломает уход
     браузера назад, и ошибка не видна.
   - Что оставить: константу модуля `_DONE = "готово"` рядом с уже объявленной
     `_STOPPED`.

6. **Запись режима бота в тестах: пять копий в одном файле.**
   - Где: `tests/backend/test_bot_aggregators.py:375-378` (`_set_mode`) совпадает
     побайтно с `tests/backend/fixtures/bot.py:85-89` (`_switch_to`). В том же
     тест-файле есть ещё три копии: `_full` (`:51-54`) и встроенные блоки на
     `:91-93` и `:294-296`.
   - Что оставить: `fixtures/bot._switch_to`. Сделать его публичным
     (`switch_to`). Тест-файл и так импортирует из `fixtures/bot`
     (`slot_freed`). `_set_mode`, `_full` и встроенные блоки заменяются вызовом.

7. **Готовая почта в тестах собирается одной строкой в четырёх местах.**
   - Где: `tests/backend/test_agent_tools_email.py:37-39`,
     `tests/backend/test_flows_aggregator_apply.py:202` и `:250`,
     `tests/client/test_bridge_apply_via.py:28` (свежий, 1a921a5). Везде
     `save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 465))`.
   - Что оставить: один построитель в общем тестовом слое, например
     `tests/factories_aggregators.py` или `tests/fakes/agent.py`:
     `async def ready_mail(session)`. Тесты самого репозитория почты
     (`test_repository_mail_account.py`) не трогать: там значения и есть предмет
     проверки.

8. **Шаги сценария агента в тестах.**
   - Где: `tests/backend/test_bot_aggregators.py:57` (`_done`) совпадает с
     `tests/backend/test_flows_aggregator_apply.py:67-70` при
     `_finish("done")`. В `test_bot_aggregators.py` тела `logged_in` (`:321`) и
     `checked` (`:337`) совпадают побайтно. В `test_flows_aggregator_seek.py`
     шаг «только finish done» встроен около семи раз.
   - Что оставить: построители `_record`, `_fail`, `_finish` перенести из
     `test_flows_aggregator_apply.py` в `tests/fakes/agent.py`, рядом с
     `scripted`, который их исполняет. Повторы зовут их.

9. **Своя медиана вместо стандартной библиотеки (правило 1, старая пара).**
   - Где: `backend/repository/stats_responses.py:106-114` (`_median`), коммит
     7dd8317 от 19.08.
   - Чем отличается: повторяет `statistics.median` и отличается только пустотой
     на пустом ряду.
   - Что оставить: `statistics.median` с проверкой пустоты у зовущего (`:143`).

### Declined to judge

- `claude_code_process.subscription_env` ↔ `claude_code_agent._env` — второе
  оборачивает первое и добавляет одну переменную; повтора нет.
- `domain/blacklist._word_match` ↔ `domain/wording.spelled_alone` ↔
  `cv_grounding._spelled_in` — правила границ разные (дефис, склонение, юникод),
  расхождение объяснено в докстроках.
- `domain/hosts.owning_host` ↔ `apply_order._owner` — первое отдаёт хост из
  отсортированного набора строк, второе — запись `KnownSite` в порядке списка;
  разные предметы и выход.
- `companies_keys.hosts_compatible` ↔ `hosts.host_owns` — равенство против
  поддомена; разные правила.
- `llm/answers.str_or_none` ↔ `incoming.text_or_none` ↔
  `client/bridge/vacancies._typed_text` — не-строку одна отбрасывает, другая
  приводит, третья не сводит пустое; объяснено в докстроках.
- `hr_card._last_company_of`/`_unread_count_of` ↔
  `hr_list._last_company_by_hr`/`_unread_by_hr` — пара «одно — много»; общее
  (`LAST_VACANCY_ORDER`, `UNREAD_INCOMING`) уже вынесено.
- `applications.has_screening` ↔ `vacancy_screening` — пара «есть ли — список»
  в одном модуле.
- `fit_preferences/_role/_languages._prompt_for` и `validate_*_fit` — разные
  наставления над общим `ask_fit`.
- `flows/ingest.save_new_vacancy` ↔ `flows/intake.save_new_vacancy` — обёртка
  над общим; имя совпадает, тела нет.
- `log_file._complain_once` ↔ `log_secrets.report_own_failure_once` — засов на
  обработчике против засова на записи; объяснено в докстроке.
- `vacancies_list._STATUS_PRIORITY_ACTIVE_FIRST` ↔
  `vacancies_mini._CHANNEL_VAC_STATUS_RANK` (и `_HOTTEST_FIRST` в тесте) —
  порядки различаются, и это подтверждено человеком 19.08; записано в обоих
  модулях.
- `site_home.make_client` ↔ `telegraph.make_client` — одно имя у разных
  адаптеров, оба на `page_client` со своими сроком и агентом.
- `deactivate_blacklisted_aggregators` ↔ `deactivate_blacklisted_channels` —
  оба на `BlacklistMark.switch_off`.
- `health.model_alive` ↔ `client/bridge/llm._client_or_reason` — расхождение
  объявлено в комментарии (слова окна против «не живо»).
- `profile_block` ↔ `agent_profile` — две разные выдачи анкеты двум читателям;
  общее (`tenure`) вынесено.
- `MailSettings` ↔ `adapters/smtp_mail.MailAccountConfig` — одинаковые поля,
  но разные состояния: черновик с пустотами и готовое к отправке.
- `client/bridge/companies.create_company_row` ↔ `hr.create_hr_row` — одна
  форма кода над разными предметами, подключены через `CardSubject`.
- Цепочка `human_done`/`reveal_browser` (`system` → `Bot` →
  `bot/aggregators` → `HumanGate`) — шов имён между мостом и ботом, а не
  повтор.
- `tools_applier._Report` ↔ `repository/applications.ApplicationEntry` — отчёт
  агента против записи; поля частично общие, предметы разные.
- `tools_seeker._posted` ↔ `incoming.moment_or_none` — первое оборачивает
  второе.
- `client/bridge/settings.APP_KEYS` ↔ `runtime_settings._APP_DEFAULTS` —
  разрешённое к записи подмножество, отдельное знание.
- Отказ «в чёрном списке» в `AGGREGATOR_REFUSALS["blacklisted"]` ↔
  `BLACKLISTED_STAYS_OFF` — разные ситуации и разные слова.
- `tools_applier`: пары «причина в `Failed`» и «ответ агенту» («почта не
  настроена», «нет файла резюме») — соседние строки для двух разных
  читателей.
- `tests/fakes/agent.apply_job` ↔ `test_agent_tools_applier._job` —
  специализация поверх общего.
- `tests/backend/fixtures/stats.rows_by_channel` ↔
  `test_repository_stats_pipeline._rows_by_source` — ключи разные (канал против
  пары канал–агрегатор).
- `tests/backend/fixtures/backfill.known_hr` ↔ `fixtures/flows.known_hr_client`
  — строка базы против подделки клиента.
- `test_agent_tools_common._Gate` ↔ `fakes/agent.silent_gate` ↔
  `test_agent_human_gate._gate` — три разных двойника под три проверки.
- Тестовые адреса-литералы (`PAGE`, `FORM`, `https://company.test/apply`) в
  нескольких тестах — данные примеров, а не общее знание.
- Тестовые `_refuse` в `tests/conftest.py` (Telegram, Anthropic, Claude Code,
  движок) — разные заслоны с разными исключениями.

### Assessment

**Ready to merge?** With fixes

**Reasoning:** Критичного нет. Свежий код этапа почти целиком стоит на готовом.
Единственный заметный повтор в свежем боевом коде — порт STARTTLS, объявленный
дважды: адаптер и репозиторий почты молча зависят от одного числа. Остальное —
мелкие повторы в одном модуле и тестовые помощники.

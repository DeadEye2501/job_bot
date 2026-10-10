# Итоговое ревью: правила проекта на питоновских тестах (174c0ca..251040f, `tests/`)

Проверены правила 13 (поведение, а не объявление), 14 (тест умеет падать) и 11 (комментарии и докстроки). Тесты не запускались. Рабочее дерево не тронуто.

## Strengths

- Почти все новые тесты смотрят на то, что видно снаружи: строки в базе (`all_rows`/`only_row`), ответ моста, ход подделки браузера (`calls`, `sending`, `as_person`), исход `run_in_slot`, план сессии, ушедший к модели запрос. Константы на равенство не сравнивает ни один.
- Повёрнутые решения («режим — только про автоматику», «Off ничего не отменяет») переписаны через следствие, а не удалением проверок. `test_entering_off_lets_the_running_round_finish` держит задачу живой после Off, отпускает её и смотрит итог `"ok"`. `test_a_run_started_by_hand_applies_in_off_too` смотрит на фазу отклика `[[41]]`.
- В тестах отказа заслона сменили причину отказа: раньше это был Off, теперь HR без адреса (`test_bot_send_effects`, `test_bot_send_refusals`). Проверки не разошлись с новым правилом и по-прежнему проверяют отказ.
- `test_the_applier_is_told_how_to_call_a_person` и `test_the_seeker_is_told_how_to_call_a_person` ищут подстроку самого правила (`need_human с kind="captcha"`), а комментарий объясняет почему: слово `need_human` есть и в промпте роли. Это образцовый комментарий по правилу 11.
- Гонки у ворот человека разобраны каждая своим тестом: стоп во время подъёма браузера, нажатие перед галочкой, нажатие после срока. Каждый тест бьёт ровно в одну ветку `HumanGate`.
- У `tests/fakes/site_home.py` настоящий клиент httpx стоит поверх подставного транспорта, и разбор страницы остаётся боевым. В докстроке названа причина подмены: сеть стенда не заперта.
- `test_a_lookalike_of_a_captcha_host_is_cut_off` и `test_a_google_form_is_an_application_not_a_captcha` закрывают оба края `_is_captcha`, а не только счастливый путь.

## Issues

### Critical

Нет.

### Important

1. **Правило 14. `tests/client/test_bridge_system.py:259-268`, `test_switching_off_cancels_nothing`.**
   - Что не так: тест фильтрует `bot.calls` по префиксу `cancel`, а ответ моста не проверяет. Из подделки `UiBot` метод `cancel_round` убран.
   - Почему это важно: самая вероятная регрессия — вернуть в `client/bridge/system.py::set_mode` строку `self._hub.bot.cancel_round()`. Тогда на подделке упадёт `AttributeError`. `reply` (`client/bridge/answer.py:137`) превратит его в `{"fail": ...}`, в `calls` ничего не появится, и тест останется зелёным. Получается, тест ловит только `cancel_current_poll`, а не возврат старого поведения.
   - Как починить: добавить `assert answer == {"ok": {"mode": "Off"}}`. Или вернуть в `UiBot` записывающий `cancel_round` и проверять `bot.calls == []`, оставив только ожидаемые вызовы вроде `kick`.

### Minor

1. **Правило 13/14. `tests/backend/test_bot_aggregators.py:616-633`, `test_a_manual_application_ignores_off_and_waits_only_for_the_slot`.**
   - Что не так: Off в тесте нигде не ставится. Он держится на том, что без строки состояния `read_mode` отдаёт `BotMode.OFF`. Проверен только путь «занято → busy». Что в Off на свободном месте отклик действительно идёт, не показано.
   - Почему это важно: читатель не видит Off. Если умолчание `read_mode` поменяют, имя теста начнёт врать, а тест останется зелёным.
   - Как починить: явно вызвать `await _set_mode(session_factory, BotMode.OFF)`. По желанию добавить второй шаг: место освобождено, исход не `"off"`.

2. **Правило 11. `tests/backend/test_bot_poll_slot.py:809-823`, `test_a_forced_poll_is_the_same_turn_as_the_cycle`.**
   - Что не так: докстрока утверждает «бот выключен — она всё равно идёт», а тест режим не ставит. Off здесь тоже только неявное умолчание.
   - Как починить: поставить Off явно или убрать эту фразу из докстроки.

3. **Правило 14. `tests/backend/test_bot_poll_slot.py:826-841`, `test_a_forced_poll_with_channels_switched_off_still_runs_the_turn`.**
   - Что не так: ингест подменён `FakeIngestion`, поэтому настоящая проверка выключателя (`backend/flows/channels.py:41`) на пути теста не стоит. Тест покраснеет только от досрочного выхода по `channels_enabled` внутри самого `force_poll_once`, а такой строки нет.
   - Почему это важно: это сторож против гипотетической правки, а не против существующей строки.
   - Как починить: в докстроке прямо назвать, от какой правки он сторожит. Или прогнать оборот через настоящий `poll_active_channels`.

4. **Правило 13. `tests/backend/test_bot_aggregators.py:669-670`, `test_the_login_check_settles_a_captcha_itself`.**
   - Что не так: первая проверка (`need_human` не в промпте) смотрит на поведение рамки, это хорошо. Вторая (`"Капча"` и `"logged_in=false"` в промпте) читает текст константы `backend/agent/prompts/login.py:7`. Это проверка объявления.
   - Как починить: вторую проверку убрать. Её смысл уже держит первая вместе с `test_the_login_check_cannot_call_for_a_human`.

5. **Правило 13. `tests/adapters/test_browser_sending.py:141`.**
   - Что не так: `any("webdriver" in script ...)` проверяет только, что в каком-то скрипте есть слово. Что скрипт прячет `navigator.webdriver`, тест не видит.
   - Почему это важно: краснеет лишь от удаления `add_init_script` целиком. Скрипт-пустышка со словом в комментарии пройдёт.
   - Как починить: тест можно принять как есть. Строже — сверять, что скрипт переопределяет свойство (`defineProperty(navigator, 'webdriver'`).

6. **Правило 11. `tests/client/test_bridge_aggregators.py:1859-1863`, докстрока `test_the_list_counts_each_source_vacancies_and_finds_by_host`.**
   - Что не так: в докстроке сказано «имя заведённого агрегатора и есть его хост». В этом же диффе имя стало браться с сайта (`create_named_aggregator`, тесты ждут `"Example"` и `"Site"`).
   - Почему это важно: довод устарел и вводит в заблуждение.
   - Как починить: «имя агрегатора берётся с сайта и может не совпадать с хостом».

7. **Правило 11. `tests/backend/test_repository_blacklist_matcher_values.py:3`.**
   - Что не так: в докстроке модуля написано «Отбор почти не различает рода», но не сказано, какой род исключён: записи агрегаторов в текстовый отбор не идут.
   - Почему это важно: слово «почти» без названного исключения ничего не объясняет.
   - Как починить: назвать исключение: «кроме сайтов: те отсеивают по адресу вакансии, а не по тексту».

## Правило 14: строка, от поломки которой краснеет каждый новый тест

**`adapters/test_browser_sending.py`**
- Обрыв POST, обрыв PUT/PATCH/DELETE, проход GET: условие `request.method in _SENDING_METHODS` в `hold_sending`.
- Капча проходит: `return any(host_owns(h, host) for h in _CAPTCHA_HOSTS)` / ветка `_GOOGLE_CAPTCHA_PATH`.
- Двойник хоста капчи обрывается: `host_owns` вместо проверки «содержит».
- Гугл-форма — отклик: ветка `if host in ("google.com", ...)`, проверяющая путь.
- Cloudflare на своём хосте: `if parts.path.startswith(_CLOUDFLARE_CHECK_PATH)`.
- Профиль без отправки: `context.route("**/*", hold_sending)` и `service_workers="block"` в `open_profile(sending=False)`.
- Вход человека: `ignore_default_args=["--enable-automation"]` и init-скрипт для `as_person`.

**`adapters/test_claude_code_agent.py`**
- `test_a_process_that_ended_on_its_own_is_put_down_quietly`: `except ProcessLookupError` в `put_down`.
- `test_the_longest_prompt_fits_a_windows_command_line`: рост рамки сверх лимита; этот тест изменён, а не новый.

**`adapters/test_smtp_mail.py`**
- `test_port_587_...`, событие `quit`: выход из `with` (прощание с сервером).
- `test_a_rude_goodbye_...`: перехват `SMTPResponseException` после принятого письма в `send_mail`.

**`backend/test_agent_human_gate.py`**
- `test_a_stop_while_the_window_comes_up_is_not_a_wait`: повторная проверка `if self._stopped: return _STOPPED` после `browser.show()`.
- `test_a_click_on_the_plate_brings_the_waiting_browser_forward_again`: `asyncio.create_task(self._show(...))` в `reveal`.
- `test_a_click_when_nobody_waits_shows_nothing` и `test_a_click_after_the_wait_expired_does_not_raise_a_browser`: условие `if self._waiting:` в `reveal`, вместе со счётом `self._waiting` в `finally`.
- `test_a_click_right_before_the_check_still_sends_the_browser_back`: `await asyncio.wait(set(self._showing))` в `_take`.

**`backend/test_agent_tools_common.py`**
- `test_the_login_check_cannot_call_for_a_human`: исключение `need_human` из набора инструментов `LoginJob` в `common_tools`.

**`backend/test_agent_tools_seeker.py`**
- Метка `web_search` в событии (оба теста): `"web_search": job.source.host is None` (`tools_seeker.py:123`).
- Сайт из отсева в `is_known` и `submit_vacancy`: `if await _barred(kit, url)` (`tools_seeker.py:91`). Для второго теста — ещё возврат «пропущена» без счёта лимита и без `refused`.

**`backend/test_bot_aggregators.py`**
- `..._lets_the_started_turn_finish`: отсутствие перечитывания режима между каналами и `launch_round` в обороте цикла.
- `test_stop_pressed_during_the_channel_poll_stops_the_whole_turn`: `if outcome != "ok" or bot.stop_event.is_set(): return` перед `launch_round`.
- `test_entering_off_lets_the_running_round_finish`: отсутствие отмены обхода в `_on_mode_switch`.
- `test_a_manual_application_ignores_off...`: отсутствие проверки режима в `apply_via_agent`; см. Minor 1.
- `test_a_login_opens_the_profile_for_a_human`: `open_profile(..., as_person=True)` в работе входа.
- `test_the_login_check_settles_a_captcha_itself`: передача в `system_prompt` набора без `need_human` для проверки входа.
- `test_a_run_started_by_hand_applies_in_off_too`: отсутствие условия режима перед фазой откликов в ручном обходе.
- `test_a_blacklisted_site_is_neither_run_nor_logged_into`: `if await repo.aggregator_blacklist_value(...) is not None: return "blacklisted"` (`aggregators.py:196`).
- Общий выключатель: `if not bot.rs.aggregators_enabled` (`aggregators.py:76`) — в `launch_round`, но не в ручном обходе.

**Остальные тесты `backend/`**
- `test_bot_chat_media`, `test_bot_chat_send`, `test_bot_read_receipts`, `test_bot_send_refusals` (Off-варианты): удалённые проверки режима в `send_to_hr_media` / `send_to_hr_chat` / `mark_hr_chat_read` / `send`.
- `test_bot_menu_actions::..._while_a_run_goes_is_refused`: проверка `slot_taken` в `ui_send_vacancy_application`.
- `test_bot_poll_slot`, оба новых теста: `await aggregators.launch_round(bot)` (`channels.py:158`). Второй — см. Minor 3.
- `test_bot_slot::test_settling_waits_for_a_window_action_in_the_slot`: ожидание любой задачи слота в `settle_slot`, а не только задач опроса.
- `test_domain_blacklist::test_a_host_matches_...`: граница образца-хоста в `check_blacklist`.
- `test_domain_hosts`:
  - `phpsessid` в списке меток сессии `source_key`;
  - тест на `assessment_id`: точное совпадение имени параметра, а не подстрока `sess`;
  - `site_label`: отбрасывание зоны и поддоменов, включая составную `co.uk`.
- `test_flows_aggregator_apply`:
  - тест правила о зове человека: передача инструментов в `system_prompt(APPLIER_PROMPT, tools)`;
  - `sending` False/True: `open_profile(..., sending=not simulated)`.
- `test_flows_aggregator_name`:
  - заглавная буква ответа модели;
  - откат с многострочного ответа на `og:site_name`;
  - часть `<title>` с меткой сайта;
  - откат на `site_label`;
  - перехват сетевой ошибки;
  - выбор `rel=icon`, затем `/favicon.ico`, отбрасывание `svg`, проверка, что ответ — картинка (а не 200 с HTML);
  - выход `"exists"` до похода на сайт.

  Каждая из этих строк — своя ветка `create_named_aggregator` / `adapters.site_home`.
- `test_flows_aggregator_seek`:
  - тест правила о зове: `system_prompt(SEEKER_PROMPT|WEB_SEEKER_PROMPT, tools)` (`aggregator_round.py:74/80`);
  - отсев в задаче: `blacklisted_sites(barred)` (`aggregator_round.py:79`).
- `test_flows_channel_walk::test_the_switch_over_all_channels_stops_the_walk`: `if not pipeline.rs.channels_enabled` (`flows/channels.py:41`).
- `test_flows_parse_verdict`, четыре теста отсева сайтов: `vacancy_barred_host(session, vacancy_id, parsed.other_contacts)` (`parse.py:345`). Для теста про контакт этого же разбора — именно аргумент `parsed.other_contacts`. Для теста про пост, только упомянувший сайт, — исключение рода `aggregator` из `load_active_blacklist_patterns`.
- `test_repository_aggregator_blacklist`: нормализация к хосту в `create_blacklist` и `update_blacklist`; гашение по `host_owns` (поддомен); `"blacklisted"` в `set_aggregator_active`; фильтр в `round_sources`; признак в перечне и карточке; кандидаты без «Поиска по сети».
- `test_repository_applications::test_the_screening_...`: порядок по `sent_at` и `position`, фильтр по `vacancy_id`, выпадение отклика без реплик в `vacancy_screening`.
- `test_repository_mail_account`: таблица почтовых пресетов в `save_mail_account`; `get_mail_account` → `None` без сервера.

**`client/`**
- `test_bridge_aggregators`: каждый тест краснеет от своей ветки домена. Это эхо `aggregator_id` в отказе `fields`; счёт и поиск по хосту в `list`; фильтр источника в `detail`/`vacancies`; `_avatar_data_url` в ответе; `set_all_active` пишет настройку, а не строки; `block`/`unblock`; отказ «Поиск по сети»; текст вести `"blacklisted"`.
- `test_bridge_apply_via::test_no_way_leads_to_a_blacklisted_site`: фильтр способов по `barred_host_of` в `apply_ways`.
- `test_bridge_blacklist`, два новых теста: нормализация рода `aggregator` при `create`.
- `test_bridge_channels::test_the_switch_over_all_...`: `set_all_active` пишет `channels_enabled`, а не `is_active` строк.
- `test_bridge_media`: таблица сигнатур в `_avatar_data_url`.
- `test_bridge_settings`: отдача `password` и вычисление `server_by_address`.
- `test_bridge_shell`: допуск схем `mailto:` и `tel:` в `open_url`.
- `test_bridge_system`:
  - `test_a_click_on_the_plate_reaches_the_bot`: `self._hub.bot.reveal_browser()`;
  - `test_switching_off_cancels_nothing`: см. Important 1.
- `test_bridge_vacancies`: `aggregator_name` / `from_web_search` / `has_screening` в карточке; домен `screening` и его отказ «Вакансия не найдена.».
- `test_bridge_vacancy_actions`: текст вести «Каналы пройдены.»; изменён, а не новый.

## Declined to judge

- `tests/backend/test_agent_prompts.py`: механическая подстановка `[]` вторым аргументом `system_prompt`. Поведение не менялось. Пропажа `need_human` в этом файле покрыта новыми тестами в `test_flows_aggregator_apply/seek`.
- `tests/backend/test_repository_vacancy_mini_lists.py`: переименование `list_vacancies_for_channel` → `list_vacancies_from`. Проверки прежние.
- `tests/backend/test_repository_aggregators.py`: новые аргументы `create_aggregator`. Суть проверок прежняя.
- `tests/backend/test_repository_channel_switching.py`, `tests/client/test_bridge_apply_via.py::test_off_mode_is_explained`: удалённые тесты. Поведение снято вместе с кодом, новых тестов там нет.
- `tests/fakes/browser.py`, `tests/fakes/ui_bot.py`, `tests/fakes/site_home.py`: подделки, а не тесты. По правилам 13/14 не оцениваются; комментарии в них проверены по правилу 11, замечаний нет.
- Что каждый тест «хоть раз был красным» (вторая половина правила 14) по диффу не проверить: тесты не запускались, мутации отменены решением человека. Судил только по тому, есть ли строка, поломка которой видна тесту.

## Assessment

**Ready to merge?** With fixes

**Reasoning:** Набор в целом добротный: тесты смотрят на следствия, повёрнутые правила переписаны через видимое поведение, комментарии объясняют неочевидное, и летописи в них нет. Слепой тест один — `test_switching_off_cancels_nothing`: он не видит самой вероятной регрессии, возврата `cancel_round()` в мосте, потому что ответ моста не проверяется. Это чинится одной строкой. Остальное мелочи: неявный Off в двух тестах, одна проверка текста константы промпта, две неточные докстроки и один сторож от несуществующей правки.

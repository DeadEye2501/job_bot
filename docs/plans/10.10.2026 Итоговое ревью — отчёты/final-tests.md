# Итоговое ревью: тесты, диапазон 174c0ca..251040f

## Strengths

- Почти все новые тесты смотрят на то, что видно снаружи: строки базы, ответы моста, зовы моста из окна, DOM смонтированного компонента, план сессии агента (промпт, задача, `web_search`), судьба запроса в браузере (`aborted`/`passed`). Тестов, которые проверяют только объявление и упасть не могут, я не нашёл.
- У проверок есть парные отрицания, и это сделано сознательно: капча проходит — а хост, похожий на капчу, и Google Forms обрываются; сайт из отсева отсеивает вакансию — а пост, который сайт просто упоминает, нет; `web_search` true на «Поиске по сети» — и false на агрегаторе; «Поиск по сети» попадает в обход — а агрегатор из отсева нет; `sending=False` для симуляции — и `sending=True` для настоящего отклика.
- Гонки проверены там, где они на самом деле бывают: ответ о способах отклика или скрининг доезжает уже к другой вакансии; ответ поиска, обогнанный свежим; второй добор, пока летит первый; проверка модели, пришедшая после правки полей или ухода с экрана; остановка, пока поднимается браузер; клик по плашке сразу перед галочкой.
- Подстрока правила о зове человека (`'need_human с kind="captcha"'`) выбрана намеренно, а не по слову `need_human`, и это пояснено комментарием. Без такой подстроки пропажу правила замаскировало бы упоминание инструмента в промпте роли.
- Старые тесты, переписанные под решение «режим только про автоматику» (`test_bot_chat_send`, `test_bot_chat_media`, `test_bot_read_receipts`, `test_bot_send_refusals`, `test_bot_aggregators`, `test_bridge_system`), не просто перевёрнуты. Каждый теперь утверждает положительный исход: письмо ушло, прочитанное погашено, обход доработал. Тесты, которым нужен был отказ заслона, теперь получают его от HR без адреса, а не от режима Off.
- Функции, у которых убраны тесты, удалены и из боевого кода: `sessionText`, `channelsToggle`, `set_all_channels_active`, `cancel_round`, `list_vacancies_for_channel`. Тесты `siteHref` и `channelStats` не потеряны, а переехали в `site.test.js` и `sources.test.js`.
- Для общего монтирования карточки вакансии заведён один помощник `vacancy_card_mount.js`. Набор свойств больше не копируется по четырём файлам.

## Runs

| Набор | Команда | Итог |
|---|---|---|
| Python | `pipenv run python -m pytest tests -q -p no:cacheprovider` | **3405 passed** за 166.81 с; падений 0, предупреждений 0 |
| Фронт | `npm test --prefix client/web` | **83 файла, 824 теста passed** за 17.69 с; падений 0 |

Каждый набор запущен ровно один раз. Падений нет, поэтому вывод падений не приводится.

## Что ловит каждый тест диапазона

Для каждого теста: что он видит снаружи → какая одна сломанная строка боевого кода сделала бы его красным (названо словами, не проверялось).

### tests/adapters/test_browser_sending.py (новый)
- `form_sending_its_data_is_cut_off`, `every_method_that_carries_data_is_cut_off` — судьба запроса `aborted` → `hold_sending` пропускает POST (или PUT/PATCH/DELETE) через `continue_`.
- `reading_pages_goes_on` — GET проходит → в правило обрыва попал и GET.
- `a_captcha_answer_still_goes_out` — POST на три хоста капчи проходит → убрана проверка хоста капчи (или один хост из списка).
- `a_lookalike_of_a_captcha_host_is_cut_off` — `hcaptcha.com.company.test` обрывается → хост сверяется вхождением строки или `startswith`, а не по концу домена.
- `a_google_form_is_an_application_not_a_captcha` — Google Forms обрываются → в разрешённые попал весь `google.com`, а не путь `/recaptcha/`.
- `cloudflare_checking_a_human_on_the_site_itself_still_goes_out` — `/cdn-cgi/challenge-platform/` на хосте сайта проходит → путь Cloudflare проверяется только на `challenges.cloudflare.com`.
- `a_profile_opened_not_to_send_holds_every_request` — у профиля без отправки есть маршрут `**/*` и блокировка service workers, у профиля с отправкой их нет → в `open_profile` выпал `context.route(...)` (или `service_workers` при `sending=False`).
- `a_profile_opened_for_a_human_login_carries_no_automation_mark` — у профиля «для человека» нет `--enable-automation`, есть скрипт про webdriver, нет лишних флагов и включена песочница; у агента ничего этого нет → не передан `ignore_default_args` (или скрипт `navigator.webdriver` не добавлен).

### tests/adapters/test_claude_code_agent.py
- `the_longest_prompt_fits_a_windows_command_line` (изменён) — длина argv < 30 000 при промпте с правилом о человеке → правило о зове человека раздулось, или наставление откликателя выросло за предел.
- `a_process_that_ended_on_its_own_is_put_down_quietly` (новый) — `put_down` не бросает → в `put_down` нет перехвата `ProcessLookupError` вокруг `kill()`.

### tests/adapters/test_smtp_mail.py
- `port_587_secures_the_line_before_the_login` (изменён) — порядок `starttls → login → quit` → вход перенесён до `starttls`.
- `a_rude_goodbye_after_an_accepted_letter_is_not_a_failure` (новый) — `send_mail` не бросает, когда сервер на прощание отвечает не 221, письмо учтено → перехват `SMTPResponseException` на `quit` снят.

### tests/backend/test_agent_human_gate.py
- `a_stop_while_the_window_comes_up_is_not_a_wait` — ответ «обход остановлен», окно не позвано → после `await show()` не перепроверяется флаг остановки.
- `a_click_on_the_plate_brings_the_waiting_browser_forward_again` — второй `show` → `reveal()` не зовёт `show`.
- `a_click_when_nobody_waits_shows_nothing` — после `resolve` лишнего `show` нет → `reveal()` не проверяет, ждёт ли кто-то.
- `a_click_right_before_the_check_still_sends_the_browser_back` — `hide` идёт после медленного `show` → `hide` вызывается, не дождавшись `show` от `reveal`.
- `a_click_after_the_wait_expired_does_not_raise_a_browser` — после истёкшего срока `show` нет → по истечении срока не снимается признак ожидания.

### tests/backend/test_agent_prompts.py (изменён только вызов `system_prompt(role, [])`)
- Тесты те же, проверка `need_human` убрана из `every_role_works_inside_the_common_frame`. Утрата не случилась: правило проверяется по подстроке в тестах `test_flows_aggregator_apply` и `test_flows_aggregator_seek`, а его отсутствие — в `test_bot_aggregators::the_login_check_settles_a_captcha_itself`.

### tests/backend/test_agent_tools_common.py
- `the_login_check_cannot_call_for_a_human` — в наборе инструментов проверки входа нет `need_human`, но есть `report_login` → `common_tools` выдаёт `need_human` и для `LoginJob`. Набор инструментов — это то, что видит агент, так что объявлением я это не считаю.

### tests/backend/test_agent_tools_seeker.py
- `a_find_on_the_open_web_is_marked_so_in_its_event` / `..._on_an_aggregator_is_not_marked...` — `payload["web_search"]` равен true или false в событии `found` → признак записан константой или не записан вовсе.
- `a_page_of_a_blacklisted_site_is_not_to_be_opened` — `is_known` отвечает «в чёрном списке, не открывай» → `is_known` не сверяет хост с отсевом.
- `a_page_of_a_blacklisted_site_is_skipped_without_costing_the_limit` — «пропущена», вакансий нет, `submitted == 0`, `refused` false → в `submit_vacancy` выпала сверка с отсевом (или пропуск считается отказом, или пропуск увеличивает `submitted`).

### tests/backend/test_bot_aggregators.py
- `off_during_the_channel_poll_lets_the_started_turn_finish` (переписан) — после Off посреди опроса обход всё равно запущен → в `_tick` вернулась перепроверка режима между каналами и агрегаторами.
- `a_stop_during_the_channel_poll_keeps_the_round_from_starting` — по `stop_event` обход не стартует → снята проверка `stop_event` перед запуском обхода.
- `stop_pressed_during_the_channel_poll_stops_the_whole_turn` (новый) — `cancel_current_poll` посреди опроса гасит и обход → `_tick` глотает `CancelledError` опроса и идёт к агрегаторам.
- `entering_off_lets_the_channel_poll_finish` — опрос дорабатывает после Off → `_on_mode_switch` отменяет текущую задачу.
- `entering_off_lets_the_running_round_finish` (переписан) — обход жив после Off и кончается `ok` → `_on_mode_switch` снова гасит обход.
- `a_manual_application_ignores_off_and_waits_only_for_the_slot` (переписан) — ответ `busy` при занятом месте → проверка режима вставлена в `apply_via_agent` до `_in_slot`. **См. Important 1:** название обещает больше, чем проверено.
- `a_login_opens_the_profile_for_a_human` — `browser.as_person is True` → `login_aggregator` открывает профиль без `as_person=True`.
- `the_login_check_settles_a_captcha_itself` — в промпте проверки входа нет `need_human`, но есть слово про капчу и `logged_in=false` → проверке входа снова передан `need_human` (или из её наставления выпала строка про капчу).
- `a_run_started_by_hand_applies_in_off_too` (переписан) — фаза откликов `[[41]]` в Off → ручной обход снова отсекает отклики по режиму.
- `a_blacklisted_site_is_neither_run_nor_logged_into` — оба зова отвечают `blacklisted`, планов нет → `run_aggregator_now` или `login_aggregator` не сверяет отсев.
- `the_switch_over_all_aggregators_keeps_the_round_from_starting` / `..._leaves_a_manual_run_alone` — общий выключатель гасит автоматический обход и не трогает ручной → `launch_round` не читает `aggregators_enabled` (или его читает и `run_aggregator_now`).

### tests/backend/test_bot_chat_media.py, test_bot_chat_send.py, test_bot_read_receipts.py, test_bot_send_refusals.py
- Каждый переписанный тест в Off видит, что действие человека прошло: файл ушёл, сообщение ушло, прочитанное погашено (`1`, `read_at` задан), отклик по кнопке ушёл (`True`, одно письмо). Красным его сделает возврат заслона по режиму в `send_to_hr_media`, `send_to_hr_chat`, `mark_hr_chat_read` или `send` соответственно.
- В `test_bot_send_effects::a_refused_send_tells_the_window_nothing` и `test_bot_send_refusals::a_refusal_leaves_no_trace_in_the_history` отказ теперь вызывает HR без адреса. Сломать их может весть окну (или запись в ленту), отправленная до заслона адреса.

### tests/backend/test_bot_menu_actions.py
- `sending_an_application_while_a_run_goes_is_refused` — `(False, "busy")` при занятом месте → `ui_send_vacancy_application` не проверяет `slot_taken`.

### tests/backend/test_bot_poll_slot.py
- `a_forced_poll_is_the_same_turn_as_the_cycle` — по ▶ идёт «недоразобранные → прогон каналов», затем `launch_round` → `force_poll_once` не вызывает `launch_round`.
- `a_forced_poll_with_channels_switched_off_still_runs_the_turn` — `ok` и обход запущен при выключенных каналах → выключенные каналы снова прерывают ▶ ранним выходом.

### tests/backend/test_bot_slot.py
- `settling_waits_for_a_window_action_in_the_slot` — `finally` действия окна успел отработать, итог `cancelled` → `settle_slot` ждёт только задачи с именем опроса или обхода и пропускает «aggregator login».

### tests/backend/test_domain_blacklist.py, test_domain_hosts.py
- `a_host_matches_inside_a_link_and_on_a_subdomain` — `superjob.ru` ловится в поддомене, `hh.ru` не ловится в `nothh.ru` → граница слова для образцов-хостов снята (или потеряно совпадение по поддомену).
- `click_session_and_arrival_marks...` (добавлен `phpsessid`), `a_parameter_that_merely_contains_sess_is_kept` → метка сессии сверяется вхождением `sess` (тогда пропадает `assessment_id`) или `phpsessid` не входит в список.
- `the_site_label_drops_the_zone_and_subdomains` (6 случаев) → `site_label` берёт первый кусок хоста (или не знает двухчастных зон вроде `co.uk`).

### tests/backend/test_flows_aggregator_apply.py
- `the_applier_is_told_how_to_call_a_person` — подстрока правила есть в промпте откликателя → откликателю не передан `need_human` (рамка тогда опускает правило).
- `a_simulated_application_is_told_not_to_send_and_is_marked` (добавлено) — `browser.sending is False` → симуляция открывает профиль с `sending=True`.
- `a_real_application_opens_the_browser_able_to_send` — `sending is True` → настоящий отклик открыт с удержанием (тогда отклики молча не уходят).

### tests/backend/test_flows_aggregator_name.py (новый)
- `the_model_answer_is_the_name_with_a_capital_letter` — имя «Пример Карьера», в запрос к модели ушла подсказка → нет заглавной буквы (или подсказки страницы не уходят модели).
- `a_rambling_model_answer_gives_way_to_the_declared_name` → многострочный ответ модели принят как имя.
- `the_title_part_naming_the_site_stands_in...`, `without_hints_and_model_the_name_is_the_site_label` → не выбирается часть `<title>`, совпадающая с меткой сайта (или нет запасного варианта «метка с заглавной»).
- `an_unreachable_site_does_not_block_creation` → `ConnectError` не перехвачен.
- `the_icon_the_page_declares_becomes_the_avatar`, `without_a_declared_icon_the_site_favicon_is_taken`, `a_vector_icon_gives_way_to_a_picture`, `a_site_without_an_icon...`, `a_page_answering_instead_of_a_picture_is_not_an_icon` → не разбирается `rel=icon`; нет запасного `/favicon.ico`; SVG не отбрасывается; 404 даёт аватар; не проверяется тип содержимого `image/*`.
- `a_known_site_is_not_asked_again` → для существующего хоста всё равно идёт сетевой запрос (тогда `ConnectError` даёт другое имя или статус).

### tests/backend/test_flows_aggregator_seek.py
- `the_seeker_is_told_how_to_call_a_person` [агрегатор / поиск по сети] → искателю не передан `need_human`.
- `the_web_seeker_hears_of_the_blacklisted_sites` / `..._that_no_site_is_blacklisted` → задача искателя не перечисляет отсев (или при пустом отсеве строка пропадает).

### tests/backend/test_flows_channel_walk.py
- `the_switch_over_all_channels_stops_the_walk` — ни один канал не пройден, тумблер строки остался true → `poll_active_channels` не читает `channels_enabled` (или выключатель переписывает `is_active`).

### tests/backend/test_flows_parse_verdict.py
- `a_vacancy_from_a_blacklisted_site_is_marked_unfit` → отсев не смотрит на `source_url`.
- `a_contact_leading_to_a_blacklisted_site_marks_the_vacancy_unfit` → отсев не смотрит на сохранённые контакты.
- `a_contact_found_by_this_very_parse_marks_the_vacancy_unfit` → не сверяются `other_contacts` текущего разбора.
- `a_post_merely_naming_a_blacklisted_site_is_not_sifted_out` — статус `NEW` → образцы рода `aggregator` попали в текстовую сверку `check_blacklist`.

### tests/backend/test_repository_aggregator_blacklist.py (новый)
- `a_typed_address_is_stored_as_the_host` / `an_address_without_a_host_is_refused` / `an_address_edited_in_place_is_stored_as_the_host_too` → `create_blacklist` или `update_blacklist` не приводит значение рода `aggregator` к хосту (или пропускает пустой хост).
- `a_mark_on_a_site_covers_its_subdomain_aggregator` → сверка хоста строгим равенством, без поддоменов.
- `an_entry_switches_the_aggregator_off`, `switching_an_entry_back_on_switches_the_aggregator_off` → после `create_blacklist` или `set_blacklist_active` не гасятся агрегаторы (проверено и на парном чистом агрегаторе).
- `a_blacklisted_aggregator_cannot_be_switched_on` → `set_aggregator_active` не сверяет отсев.
- `the_round_skips_a_blacklisted_aggregator_even_when_switched_on` → `round_sources` не фильтрует по отсеву (или отсеивает и «Поиск по сети»).
- `the_list_and_the_card_show_the_mark` → признак не попадает в перечень или карточку.
- `aggregators_are_suggested_by_host` → «Поиск по сети» попадает в подсказки (или неверна подпись или порядок).

### tests/backend/test_repository_aggregators.py, test_repository_applications.py, test_repository_mail_account.py, test_repository_vacancy_mini_lists.py, test_repository_channel_switching.py
- `an_address_is_stored_as_its_host_under_the_given_name` → `create_aggregator` пишет хост вместо переданного имени.
- `the_screening_of_a_vacancy_goes_application_by_application` → нет сортировки по `sent_at` или по порядку реплик (или в выборку попали отклики без скрининга или чужие).
- `popular_mail_needs_no_server` (6 случаев), `unknown_mail_without_a_server_cannot_send` → не хватает записи в таблице известных почт (или незнакомая почта получает выдуманный сервер).
- В `vacancy_mini_lists` и `channel_switching` изменены только сигнатуры или убраны тесты удалённой функции. Ловят они то же, что и до диапазона.

### tests/client/*
- `test_bridge_aggregators`: заведение с именем «Site» без сети → не вызвано именование; отказ тумблера с эхом номера → в отказ `fields` не кладётся `aggregator_id`; счёт и поиск по хосту → поиск только по имени (или счёт берёт и неразобранные); мусорный запрос перечня → мусор не приводится к пустому поиску; числа карточки → статистика не отфильтрована по агрегатору; значок `data:image/` в перечне и карточке → аватар не вшит; карточка 404 с номером, страница вакансий только своего агрегатора, `fields` без номера; общий выключатель не трогает строки и возвращается → `set_all_active` переписывает `is_active`; занесение в отсев, запрет включения, снятие, отказ для «Поиска по сети», слово про отсев → по одной ветке моста на каждый тест.
- `test_bridge_apply_via::no_way_leads_to_a_blacklisted_site` → `apply_ways` не отсеивает кнопку агрегатора и форму на поддомене отмеченного сайта.
- `test_bridge_blacklist` (2) → мост не приводит адрес к хосту, или текст отказа другой.
- `test_bridge_channels::the_switch_over_all_leaves_each_row_as_it_was` → общий выключатель каналов переписывает строки.
- `test_bridge_media::the_data_url_names_the_type_of_its_bytes` (5) → тип в `data:` захардкожен (как прежний jpeg) или не распознан один из форматов.
- `test_bridge_settings`: пароль возвращается и `server_by_address` → мост снова прячет пароль (или признак считает неверно).
- `test_bridge_shell::a_mail_and_a_phone_contact_open_too` → `open_url` пропускает только http, https и tg.
- `test_bridge_system::switching_off_cancels_nothing` → `set_mode` снова зовёт `cancel_*` (см. Minor 1); `a_click_on_the_plate_reaches_the_bot` → `reveal_browser` не проброшен.
- `test_bridge_vacancies`: имя агрегатора в карточке, `from_web_search`, `has_screening`, скрининг по откликам, отказ для пропавшей вакансии → по одному полю или ветке `detail` и `screening`.
- `test_bridge_vacancy_actions::a_finished_run_says_so...` → весть звучит до конца каналов, или текст другой.

### client/web/tests (фронт)
- `aggregators.test.js` — подписи «где ищет» и «последний обход»; тумблер (без входа, отсев важнее входа, общий выключен — `muted` и положение сохранено); порядок причин запора (отсев > идёт обход > слова моста > лампа) → порядок проверок в `actionBlock` или `aggregatorToggle` переставлен (или одна ветка выпала).
- `blacklist.test.js` (выпадающий род) → `kindOptions` без числа; `kindPicked` или `kindIndex` расходятся с порядком.
- `bottom_bar_live.test.js` — плашка встаёт вместо полос, клик по плашке зовёт `system.reveal_browser`, галочка зовёт `human_done`, подпись хода «(3/10)», слово обхода уходит плашкой → полоса не смотрит на `round.human`; клик не проброшен; `caption` без счёта; `round_note` не подписан.
- `card_finish.test.js::ответ, просящий подтверждения...` → `cardFinish` не смотрит на `held(done)`.
- `channels.test.js` (переписан под общий выключатель) → `channelToggle` игнорирует второй аргумент `enabled`.
- `confirm_tone_live.test.js` → кнопка удаления не `danger`.
- `contact_adding.test.js` — отказ остаётся в окне, закрытие стирает, при удаче слово строится до очистки, `null` не закрывает, `saving` снимается, пустое и двойное нажатие не уходят → по одной ветке `create()` на тест.
- `contacts_watch.test.js` → порядок «сброс, потом чтение» или отписка от вестей.
- `footer.test.js::humanText` → текст плашки.
- `new_card.test.js` → `named` пропускает пробелы; `done` берёт набранное вместо хоста из ответа.
- `paging.test.js::detailScrolled` → нет порога у низа (или нет защиты от `null`).
- `profile.test.js` — пробел и неразрывный пробел (байты `C2 A0` в литерале проверены) выкидываются из суммы, грейды и форматы уходят массивами, `blankProfile` → `profileSheet` чистит только обычный пробел (или не превращает `Set` в массив).
- `provider_form.test.js` — перечень моделей, предустановка, смена источника, выбор файла (отмена, отказ, ушли с экрана), «как у чата», проверка (busy, ok, err, ответ после правки, после ухода), беды полей → по одной ветке `providerForm` на тест. Все зовы идут через поддельный мост, проверяется состояние формы.
- `round.test.js` → конец без начала зовёт подписчика; отписанный не снимается; `human` не гаснет с концом прогона.
- `settings.test.js` (`probeLine`, `embedReading`) → неверный тон или текст; галочка «как у чата» для Claude.
- `settings_screen_live.test.js` — лимит показан и уходит зажатым до 500; «Не подключена»; адрес и пароль точками; адрес уходит `save_mail` с обрезкой и перечитывается; поля сервера видны только без `server_by_address`; справка и ссылка `id.yandex.ru`; кнопки в шапке секций; строки о сеансе нет → по одной ветке экрана на тест.
- `site.test.js` (перенос), `sources.test.js` (перенос `channelStats` и `masterToggle`) → то же, что до переноса.
- `source_card.test.js`, `source_list.test.js`, `source_vacancies.test.js` — обогнанные ответы, перечитывание столькими строками, сколько показано, добор со смещением, сброс → по одной ветке общей машины на тест.
- `source_row_live.test.js` (`describe.each` по двум родам строк) → строка агрегатора не открывается по кружку, счёту или Enter (или тумблер всплывает в `onpick`).
- `stats.test.js`, `stats_channels_card_live.test.js` → ключ строки по `id` (агрегаторы дают повтор); `target` агрегатора ведёт во вкладку каналов.
- `tg_login_dialog_live.test.js` → поле не `password` или глаз не переключает; набранное не уходит в `onsubmit`.
- `vacancies.test.js::pasteLock`, `vacancies_screen_new_live.test.js` → вставка текста не запирается во время обхода (или запирается и форма по полям).
- `vacancy_actions.test.js` — без HR отклик не заперт, обход запирает отклик и переразбор, пилюля источника (канал, агрегатор, «Сайт», нет), `applyChoices` и `noChoiceReason` → по одной ветке на тест.
- `vacancy_apply_live.test.js` — единственный способ уходит сразу; единственный Telegram уходит через `send_application`; выбор из нескольких; без выбора не подтвердить; ответ к уже другой вакансии не уходит; во время обхода `apply_ways` не спрашивается → по одной ветке обработчика «Откликнуться».
- `vacancy_card.test.js` (лента) → неверная строка события агрегатора (`found` с `web_search`, `applied_elsewhere`, `apply_failed`, `vacancy_closed`).
- `vacancy_card_live.test.js::нажатие на название...` → клик не пишет в буфер обмена (или нет слова «Название скопировано»).
- `vacancy_contacts.test.js` → `contactHref` не распознаёт почту или телефон, пропускает `javascript:`, путает порт со схемой.
- `vacancy_screening_live.test.js` — место пункта в меню, серый пункт не зовёт мост, пузыри с `me` для наших реплик, поздний ответ не открывает окно → по одной ветке.
- `words.test.js` → `vacancyCount` склеивает не те формы (сам `plural` с 11–14 проверен в `skills.test.js`).

## Issues

### Critical (Must Fix)

Нет.

### Important (Should Fix)

1. **`tests/backend/test_bot_aggregators.py::test_a_manual_application_ignores_off_and_waits_only_for_the_slot`: название обещает больше, чем проверено.** Режим Off в тесте не задан явно, он берётся из умолчания базы (`write_mode` вызывается только в соседних тестах). Место прогона занято, и тест видит только ответ `busy`. В Off ручной отклик здесь до работы не доходит. Красным тест сделает заслон режима, вставленный в `apply_via_agent` до `_in_slot`. Заслон в другом месте он не поймает: в `work`, в `_in_slot` после проверки места или внутри `apply_vacancy`. Других тестов на `apply_via_agent` в Off нет: `test_a_manual_application_tells_when_no_way_worked` переводит бота в `DM_ONLY`. А это ключевое решение человека «режим — только про автоматику». Поправить так: записать `BotMode.OFF` явно и добавить вариант со свободным местом, который в Off доходит до `exhausted` или `ok`.

### Minor (Nice to Have)

1. **`tests/client/test_bridge_system.py::test_switching_off_cancels_nothing`** фильтрует вызовы по префиксу `cancel`. Если `set_mode` снова начнёт гасить работу через `request_stop()`, тест останется зелёным. Он также не проверяет, что ответ `ok`. На уровне бэкенда то же поведение надёжно держит `test_entering_off_lets_the_running_round_finish`, поэтому ущерб небольшой. Правильнее проверять `bot.calls == [("kick",)]` или «нет ни одного зова, кроме пробуждения».
2. **`client/web/tests/source_list.test.js` → «переключатель строки говорит, легло ли, и список перечитан»** проверяет только неудачу (`setActive` вернул `null` → `false`). Ветка удачи (`true`) не проверена, хотя её обещает название.
3. **Проверки по литералам промпта** («Капча», `logged_in=false`, «Сайты в чёрном списке: нет», `'need_human с kind="captcha"'`) покраснеют от переформулировки промпта без изменения поведения. Это осознанная цена: промпт — единственное, что видит агент. Подстрока для правила о человеке выбрана обоснованно. Отмечаю только для сведения.
4. **`client/web/tests/vacancy_card_live.test.js`** переопределяет `navigator.clipboard` через `Object.defineProperty` и не восстанавливает его. Сейчас это безвредно, потому что окружение у каждого файла своё. Но следующий тест того же файла, который полагается на настоящий буфер, получит подделку.

## Declined to judge

- `tests/backend/test_repository_vacancy_mini_lists.py` (5 тестов): изменена только сигнатура (`list_vacancies_for_channel` → `list_vacancies_from(...)`). Что они ловят, не изменилось, и в этом диапазоне это не предмет ревью.
- `tests/backend/test_repository_channel_switching.py`: тесты удалённой `set_all_channels_active` убраны вместе с функцией (проверил grep, её больше нет). Оставшиеся не менялись, правились только докстроки.
- `tests/backend/test_repository_blacklist_matcher_values.py`: правка только в докстроке.
- `tests/fakes/browser.py`, `tests/fakes/site_home.py`, `tests/fakes/ui_bot.py`, `client/web/tests/vacancy_detail.js`, `client/web/tests/vacancy_card_mount.js`: это опоры, а не тесты. Я оценивал их только через тесты, которые на них опираются.
- `client/web/tests/companies.test.js`: удалены только тесты `siteHref`, которые дословно переехали в `site.test.js`.

## Assessment

**Ready to merge?** With fixes

**Reasoning:** Оба набора зелёные (Python 3405, фронт 824), и почти каждый новый тест смотрит на видимое следствие, а парные отрицания проверяют обе стороны правила. Исправить стоит один тест, чьё название обещает больше проверенного: ручной отклик в Off так ни разу и не доходит до работы. Это центральное решение этапа, а у теста нет ни явного Off, ни варианта со свободным местом.

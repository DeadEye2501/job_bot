# Карта фронта

Собрана из кода. Число в скобках — строк в файле.

## api — 2 файлов

### api/bridge.js (91)
- * Отказ моста — один на все его роды. * * Род один нарочно: экран показывает отказы единой плашкой и по роду не * ветвится. Различает их фраза, а поля рядом говорят, к какой строке отказ * относится, — по ним экран откатывает отметку, поставленную заранее.
- отдаёт: Refused, call, ready

### api/events.js (106)
- * Слушатель вестей поверх зова, который спрашивает мост «что нового после N». * * Зов приходит доводом, а не берётся отсюда: так цикл проверяется без окна и * без моста вовсе, а другого способа его проверить нет — он бесконечен по * устройству.
- отдаёт: listener

## app — 25 файлов

### app/BlacklistList.svelte (212)
- —
- принимает: ask, say, events

### app/ChannelCard.svelte (303)
- Легенда под полосой: одиннадцать цветов без подписей не читаются, а подписать отрезки внутри полосы негде.
- принимает: ask, say, lockedTip, events, channelId, onvacancy, onclose, onchanged

### app/ChannelsList.svelte (182)
- Один переключатель на весь список: он же и показывает, все ли каналы опрашиваются.
- принимает: ask, say, lockedTip, events, onvacancy
- берёт: ./ChannelCard.svelte

### app/CompaniesList.svelte (141)
- —
- принимает: ask, say, events, open, onopened, onperson, onvacancy
- берёт: ./CompanyCard.svelte

### app/CompanyCard.svelte (317)
- Написания: под ними компания приходит в объявлениях. Потеряй карточка одно из них — следующая вакансия завела бы компанию заново.
- принимает: ask, say, companyId, onperson, onvacancy, onclose, onchanged

### app/ContactsScreen.svelte (71)
- —
- принимает: ask, say, lockedTip, events, openCard, onopened, onvacancy
- берёт: ./BlacklistList.svelte, ./ChannelsList.svelte, ./CompaniesList.svelte, ./PeopleList.svelte

### app/LogsScreen.svelte (196)
- —
- принимает: ask, events, say

### app/PeopleList.svelte (139)
- —
- принимает: ask, say, events, open, onopened, oncompany, onvacancy
- берёт: ./PersonCard.svelte

### app/PersonCard.svelte (322)
- Своя запись на каждого человека: поле запечатывает номер при заведении, и заводиться заново на каждого его заставляет именно `{#key}` — без него запечатанный номер протухнет.
- принимает: ask, say, events, personId, oncompany, onvacancy, onclose, onchanged
- берёт: ./PersonChat.svelte

### app/PersonChat.svelte (246)
- Строка отправки остаётся на месте и при заслоне, только запертой: пропав, она не сказала бы, почему писать нельзя.
- принимает: ask, say, card, events, onread

### app/ProfileCv.svelte (212)
- —
- принимает: ask

### app/ProfileExperience.svelte (135)
- —
- принимает: ask

### app/ProfileScreen.svelte (30)
- —
- принимает: ask
- берёт: ./ProfileCv.svelte, ./ProfileExperience.svelte, ./ProfileSkills.svelte

### app/ProfileSkills.svelte (148)
- —
- принимает: ask

### app/SettingsScreen.svelte (346)
- Окно входа стоит внутри поля настроек, а не рядом с ним: кнопки в нём той же плотности, что и остальные кнопки экрана, и берут они её отсюда. На раскладку это не влияет — окно висит поверх страницы.
- принимает: ask, say
- берёт: ./TelegramLogin.svelte

### app/Shell.svelte (425)
- Подсказка только у запертого переключателя: у отпертого рядом стоит сам режим словом, и объяснять, что по нему нажимают, нечего.
- берёт: ./ContactsScreen.svelte, ./LogsScreen.svelte, ./ProfileScreen.svelte, ./SettingsScreen.svelte, ./StatsScreen.svelte, ./VacanciesScreen.svelte, ./WizardScreen.svelte

### app/StatsScreen.svelte (123)
- Числа считает бот, а не окно: пересчитать за тот же срок иначе нечем — пришлось бы уходить в другой раздел и возвращаться.
- принимает: ask, onslice, onchannel

### app/TelegramLogin.svelte (88)
- Окно пересоздаётся на смене шага: код и облачный пароль — разные секреты, и набранный код не должен доехать до поля пароля.
- принимает: creds, relogin, ondone, onclose

### app/VacanciesScreen.svelte (259)
- —
- принимает: ask, say, lockedTip, events, oncontacts, open, onopened, openFilter, onfiltered
- берёт: ./VacancyCard.svelte

### app/VacancyCard.svelte (386)
- Совпавшее с анкетой подсвечено: по нему видно, чем вакансия набрала свою оценку.
- принимает: ask, say, events, lockedTip, vacancyId, oncontacts, onclose, onchanged
- берёт: ./VacancyLinks.svelte

### app/VacancyLinks.svelte (131)
- —
- принимает: ask, say, vacancyId, kind, prefill, current, onclose, onlinked

### app/WizardCv.svelte (151)
- —
- принимает: ask, busy, onback, onnext

### app/WizardLlm.svelte (325)
- —
- принимает: ask, kind, onback, onnext

### app/WizardScreen.svelte (150)
- Приглушена только обложка: на финале четыре галочки горят в полную силу — это и есть то, ради чего мастер проходили.
- принимает: ask, say, ondone
- берёт: ./WizardCv.svelte, ./WizardLlm.svelte, ./WizardTelegram.svelte

### app/WizardTelegram.svelte (122)
- —
- принимает: ask, onback, onnext
- берёт: ./TelegramLogin.svelte

## components — 67 файлов

### components/ActionsMenu.svelte (31)
- —
- принимает: children

### components/AddBlacklistDialog.svelte (125)
- svelte-ignore a11y_autofocus
- принимает: draft, hints, kinds, saving, onkind, onvalue, onreason, onadd, onclose
- берёт: ./ModalKeys.svelte

### components/AddChannelDialog.svelte (48)
- svelte-ignore a11y_autofocus
- принимает: value, trouble, saving, oninput, onadd, onclose
- берёт: ./ModalKeys.svelte

### components/AskDialog.svelte (44)
- Окно берёт на себя Escape, но не Enter: в нём набирают заметки в несколько строк, и подтверждение по Enter обрывало бы заведение на первом же переводе строки.
- принимает: icon, title, subtitle, confirmLabel, ready, onconfirm, oncancel, children
- берёт: ./ModalKeys.svelte

### components/Avatar.svelte (20)
- —
- принимает: avatar, name, icon

### components/BlacklistMenuItem.svelte (26)
- —
- принимает: blocked, close, onblock, onunblock

### components/BlacklistRow.svelte (113)
- —
- принимает: row, onedit, ontoggle, onremove

### components/BulletList.svelte (51)
- —
- принимает: label, addLabel, items, onedit, onadd, onremove

### components/ChannelRow.svelte (49)
- Канал из отсева включить нельзя: обход всё равно его пропустит, и включённый переключатель обещал бы работу, которой не будет.
- принимает: channel, selected, onpick, ontoggle
- берёт: ./Avatar.svelte

### components/ChatBubble.svelte (60)
- Вложение открывает система, а не страница: мост отдаёт путь к нему адресом `file://`, а страницу раздаёт сервер окна из своей папки — ссылкой такой путь не открылся бы. Файла может и не быть вовсе: бот скачивает не всё, — и тогда остаётся род вложения в скобках, потому что открывать нечего.
- принимает: message, onopen

### components/Chip.svelte (14)
- —
- принимает: text, onremove

### components/ChipList.svelte (55)
- svelte-ignore a11y_autofocus
- принимает: items, onadd, onremove
- берёт: ./Chip.svelte

### components/ChoiceRow.svelte (27)
- —
- принимает: options, chosen, look, dots, onpick

### components/CompanyRow.svelte (43)
- —
- принимает: company, selected, onpick
- берёт: ./Avatar.svelte

### components/ConfirmDialog.svelte (22)
- —
- принимает: message, confirmLabel, onconfirm, oncancel
- берёт: ./ModalKeys.svelte

### components/CvFileRow.svelte (24)
- Открывать нечего, когда файла нет на диске: система показала бы свою ошибку вместо нашей строки «файл не найден».
- принимает: meta, onreplace, onopen

### components/DatePicker.svelte (129)
- —
- принимает: value, onpick, disabled, up

### components/DonutChart.svelte (42)
- —
- принимает: parts, total, label

### components/Dropdown.svelte (45)
- —
- принимает: options, value, onpick

### components/ExperienceCard.svelte (144)
- Нажимается вся шапка, а не одна стрелка: свёрнутых карточек столбик, и целиться в значок ради раскрытия человеку не за что.
- принимает: exp, known, open, ontoggle, onedit, onremove
- берёт: ./BulletList.svelte, ./DatePicker.svelte, ./SkillPicker.svelte

### components/FilterGroup.svelte (12)
- —
- принимает: label, children

### components/HealthLamp.svelte (9)
- —
- принимает: name, state, title

### components/LangRows.svelte (49)
- —
- принимает: rows, onedit, onadd, onremove
- берёт: ./Dropdown.svelte

### components/LlmSection.svelte (108)
- Ввод в любое из полей гасит плашку проверки: она говорит «модель отвечает» про тот адрес, который проверяли, и на изменённых полях лгала бы. Ловится здесь, а не на каждом поле: событие всплывает, и второй обработчик у поля секрета пришлось бы заводить внутри чужого компонента.
- принимает: title, icon, creds, models, pill, busy, sameAsChat, onsave, onprobe, onsame, onedit
- берёт: ./SecretInput.svelte, ./SettingsSection.svelte, ./SuggestInput.svelte

### components/LogLevelPill.svelte (17)
- —
- принимает: label, icon, tone, count, active, onpick

### components/LogRow.svelte (17)
- svelte-ignore a11y_click_events_have_key_events
- принимает: time, level, tone, source, message, details, expanded, ontoggle

### components/MiniPeople.svelte (39)
- —
- принимает: people, empty, onpick
- берёт: ./Avatar.svelte

### components/MiniVacancies.svelte (40)
- —
- принимает: vacancies, empty, loading, onpick

### components/ModalKeys.svelte (17)
- —
- принимает: close, confirm

### components/ModeToggle.svelte (29)
- —
- принимает: mode, disabled, title, onpick

### components/NavGroup.svelte (9)
- —
- принимает: icon, label, active, onpick

### components/NewCompanyFields.svelte (39)
- —
- принимает: draft

### components/NewPersonFields.svelte (37)
- Номер учётной записи — только цифры: на телефоне открывается цифровая раскладка, а мост всё равно приводит его к числу.
- принимает: draft

### components/NotesField.svelte (64)
- —
- принимает: value, placeholder, delay, limit, owner, save

### components/PersonRow.svelte (53)
- Ник и компания — то, чем различают тёзок: по нику находят в Telegram, по компании вспоминают, откуда человек писал. Обе половины названы всегда: пустое место читалось бы как недогрузившаяся строка.
- принимает: person, selected, onpick
- берёт: ./Avatar.svelte

### components/PickList.svelte (55)
- —
- принимает: placeholder, hint, empty, names, chosen, search, onsearch, prefix, onpick

### components/PickerDialog.svelte (159)
- Пустых слов два, и разница несущая: «ничего не найдено» говорит, что список есть, а показать из него нечего, — и человек ищет причину в поле поиска, а не в том, что заводить он ещё ничего не начинал.
- принимает: title, icon, placeholder, empty, prefill, current, preselect, load, applyLabel, onapply, saving, onclose, children, createLabel, createIcon, oncreate
- берёт: ./ModalKeys.svelte

### components/PickerRow.svelte (34)
- —
- принимает: row, current, chosen, mark, onpick
- берёт: ./Avatar.svelte

### components/PipelineSection.svelte (113)
- Поля нет — значит выключена, как и в настройках бота: включённая молча, она показывала бы «отклик отправлен» над письмом, которого HR не получал. Стенд включают нарочно.
- принимает: values, onsave
- берёт: ./SettingsSection.svelte

### components/Plaque.svelte (9)
- —
- принимает: message, danger

### components/ProgressBars.svelte (25)
- —
- принимает: channels, messages, text

### components/RawTextDialog.svelte (50)
- Кнопка стоит поверх текста и полупрозрачна: окно узкое, и вынесенная в подвал она отняла бы у текста строку ради того, что нажимают раз в десять открытий.
- принимает: id, chips, text, oncopy, onclose
- берёт: ./ModalKeys.svelte

### components/RunButton.svelte (13)
- —
- принимает: running, disabled, title, onpress

### components/SearchBox.svelte (33)
- —
- принимает: value, placeholder, onsearch

### components/SecretInput.svelte (27)
- —
- принимает: value, placeholder, onsave

### components/SettingsSection.svelte (17)
- —
- принимает: icon, title, pill, danger, children
- берёт: ./StatusPill.svelte

### components/SkillPicker.svelte (93)
- —
- принимает: chosen, known, onadd, onremove
- берёт: ./Chip.svelte

### components/SkillRow.svelte (51)
- —
- принимает: skill, onedit, onremove
- берёт: ./ChipList.svelte

### components/StatsCard.svelte (15)
- —
- принимает: title, ready, span, children

### components/StatsChannelsCard.svelte (83)
- —
- принимает: channels, onpick

### components/StatsKpiRow.svelte (30)
- —
- принимает: answer, period

### components/StatsResponsesCard.svelte (42)
- —
- принимает: answer

### components/StatsSkillsCard.svelte (30)
- —
- принимает: skills

### components/StatsStatusCard.svelte (41)
- —
- принимает: counts, onpick
- берёт: ./DonutChart.svelte

### components/StatusPicker.svelte (69)
- Заперты на время записи обе: пока ответ в пути, отмена оставила бы человека думать, что перехода не было, — а он уже уехал.
- принимает: status, saving, wrap, onapply, oncancel

### components/StatusPill.svelte (6)
- —
- принимает: text, tone, title

### components/SuggestInput.svelte (71)
- Нажатие не уводит из поля: уйди оно — сработал бы уход, поле записало бы набранное, и выбранное имя уехало бы наверх вторым зовом поверх первого.
- принимает: value, options, placeholder, mono, maxlength, onsave

### components/TelegramSection.svelte (51)
- —
- принимает: tg, draft, busy, onedit, onlogin, onlogout
- берёт: ./SecretInput.svelte, ./SettingsSection.svelte

### components/TgLoginDialog.svelte (61)
- Escape закрывает, Enter — нет: шаг уходит только кнопкой.
- принимает: step, phone, relogin, busy, error, onsubmit, oncancel
- берёт: ./ModalKeys.svelte

### components/TopTabs.svelte (12)
- —
- принимает: tabs, active, onpick

### components/UnreadBadge.svelte (49)
- Затемнения нет вовсе, но нажатие мимо список закрывает: он висит поверх окна, и оставленный открытым перекрывал бы правый край полосы.
- принимает: count, open, loading, rows, ontoggle, onpick

### components/VacancyActions.svelte (78)
- —
- принимает: blocks, say, onsend, onrerun, onlinkhr, onlinkcompany, onraw, onsource, ondelete
- берёт: ./ActionsMenu.svelte

### components/VacancyFilters.svelte (260)
- Панель падает из полосы, а не из-под кнопки: она вдвое шире полосы, и прижатая к кнопке у правого края она уходила бы за кромку списка.
- принимает: applied, options, onapply, shown, onshown
- берёт: ./ChoiceRow.svelte, ./DatePicker.svelte, ./FilterGroup.svelte, ./PickList.svelte

### components/VacancyRow.svelte (38)
- Половины подписи покрашены по-разному: компанию читают первой, а давность — последней, и одинаковый цвет заставлял бы разбирать строку целиком.
- принимает: vacancy, threshold, selected, onpick

### components/VacancyTimeline.svelte (112)
- —
- принимает: rows, vacancyId, onsave

### components/WizardFoot.svelte (39)
- Заперта вместе с основной: уход назад посреди зова оставил бы ответ прилетать в экран, которого уже нет.
- принимает: trouble, nextLabel, nextIcon, busy, onback, onnext, children

### components/WizardSteps.svelte (16)
- —
- принимает: marks, dimmed

## state — 31 файлов

### state/attempts.js (38)
- * Завести свой счёт попыток. * * Заводится он на каждое место, где запросы обгоняют друг друга, — поиск, * прокрутка, переключение вкладок. Общий счётчик на страницу отбрасывал бы * ответы соседнего экрана. * * Отмена не останавливает уже начатую работу — остановить её со страницы * нечем, — а обесценивает её ответ: пришедший последним не считается свежим, * если после него успели спросить заново. * * **Это не про закрытие окна.** Свежим тут считается ровно один запрос, а окно * спрашивает мост вперемешку — здоровье, непрочитанное, режим, — и соседний * ответ такой счёт объявил бы устаревшим. Уход со страницы оболочка сторожит * своим признаком: там гасится всё разом, а не последнее.
- отдаёт: attempts

### state/autosave.js (58)
- * Заводит отложенную запись поля. * * Пауза считается от последнего знака: запись на каждый знак послала бы мосту * по вопросу на букву, а отсчёт от первого отправлял бы недописанное.
- отдаёт: autosave

### state/calendar.js (62)
- * Дни недели с понедельника. Порядок несущий: по нему считается, в какую * колонку встаёт первое число месяца.
- отдаёт: WEEKDAYS, monthGrid, monthTitle, shiftMonth

### state/card_links.js (25)
- * Три связи карточки: две внутрь и одна в подборщик. * * Пустая связь названа пустотой, а не пропущена: карточка ставит на её место * неподвижную подпись, и разбирать, чего в ответе нет, ей было бы нечем. * * Имя компании без привязки ведёт не в контакты, а в подборщик с этим самым * именем: связи нет, но разбор её узнал — человек нажимает и сразу видит * совпадения, вместо того чтобы набирать то же слово руками.
- отдаёт: cardLinks

### state/chat.js (108)
- * Разложить письма по дням, сохранив их порядок. * * Подпись дня стоит над первым письмом этого дня, а не над каждым: иначе лента * превращается в чересполосицу дат. * * Письмо без времени выпадает вовсе — поставить его некуда, а под чужой * подписью дня оно соврало бы.
- отдаёт: attachmentKind, byDays, chatTime, sendBlock, tick, unread

### state/chosen.js (27)
- * Какую долю дорожки залить под это значение. * * Зажато с обеих сторон: значение приезжает с моста и могло быть выставлено * до того, как предел назначили, — заливка шире дорожки выглядит поломкой, а * отрицательная не рисуется вовсе.
- отдаёт: fillPercent, toggled

### state/companies.js (68)
- /i; /** Чем подписать компанию в списке. * * Имя — сверху, сайт и алиасы — под ним: по имени компанию узнают, по * домену различают. Две «Ромашки» с разными сайтами — разные компании, и без * второй строки они неотличимы. * * Имени может не быть — оно приходит из объявления, — и тогда компания названа * номером: показать нечего, но строка должна остаться нажимаемой.
- отдаёт: companyCandidate, companyLine, siteHref

### state/contacts.js (305)
- * Роды строк отсева. Первый — общий: в нём экран открывается. * * Порядок несущий: слова стоят перед предметами, потому что ими отсев и * пользуются чаще всего — по одному слову отсеивается больше объявлений, чем по * всем каналам вместе.
- отдаёт: BLACKLIST_KINDS, blacklistCounts, blacklistHints, blacklistShown, channelName, channelStats, channelToggle, channelsToggle, fresher, initials, linkReady, named, personCandidate, personLine, personName, pollBlock, telegramHref, unreadLine, valueField

### state/dates.js (102)
- * Дата для тесной колонки: день, сокращённый месяц и год чужого года. * * Год этого года не пишется: он и так известен, а колонка узка. Негодное и * пустое дают пустоту — прочерк в такой колонке читался бы как значение.
- отдаёт: asIso, dayOf, isoDay, shortDate, showDate, showStamp, validDate

### state/experience.js (32)
- * Период работы для шапки карточки. * * Месяц и год без дня: места работы различают по месяцам, а день удлиняет * строку вдвое. Открытый конец назван словами — по нему и читают, работает * человек здесь сейчас или нет.
- отдаёт: cardTitle, period

### state/flash.js (24)
- * Заводит отметку, которая гаснет сама. * * Второе зажигание подряд отсчёт продлевает, а не гасит: быстрая правка двух * полей иначе тушила бы рамку по времени первого, и вторая запись выглядела бы * незаписанной.
- отдаёт: flashing

### state/health.js (65)
- * Живо ли всё, на чём держится работа бота. * * По этому ответу отпираются кнопки режима и запуска, поэтому незнание считается * «не живо»: до первого ответа моста мы не знаем ничего, а отпертая на миг * раньше правды кнопка запускает бота без модели.
- отдаёт: LAMPS, allAlive, blockedTip, downNames, shouldTurnOff

### state/keys.js (55)
- * Чем нажатая клавиша отзовётся в окне: закрытием, подтверждением или ничем. * * Многострочное поле — исключение: в нём Enter переносит строку. Иначе заметку * в два абзаца не набрать, первый же перевод строки отправил бы окно.
- отдаёт: modalKey, modalPress, opened, saveKey

### state/logs.js (103)
- * Уровни на пилюлях — от беды к мелочи. Порядок постоянный: по нему человек * метит в нужную пилюлю, не читая подписей. * * `id` — то, что приходит в записи с питона; `tone` — имя цвета; значок * лигатурой шрифта. `CRITICAL` своей пилюли не имеет: его накрывает `ERROR`.
- отдаёт: AT_FIRST, LEVELS, askDelay, emptyText, levelTone, logTime, mayHide, shown

### state/modes.js (26)
- * Три положения слева направо. Порядок несущий: по нему считается, в какую * треть дорожки попало нажатие.
- отдаёт: OFF, modeAt

### state/outside.js (31)
- * Ставит сторожа «нажали мимо» и отдаёт его снятие. * * Отдаётся снятие затем, что зовут это из эффекта: он и вернёт его окну. * * Узла может ещё не быть — разметка привязывает его после первого показа, — и * до тех пор мимо не нажимают ни разу: окошка на экране нет.
- отдаёт: closeOnClickAway

### state/paged_list.svelte.js (119)
- * Заводит список, читающий себя страницами. * * `ask` — обращение к мосту, `method` — имя метода, `key` — под каким именем * строки лежат в ответе.
- отдаёт: pagedList

### state/paging.js (65)
- * Сколько строк в странице. Столько же по умолчанию отдаёт мост.
- отдаёт: PAGE, VACANCY_PAGE, appended, nearBottom, nearTop, refreshLimit

### state/profile.js (109)
- * Грейды, какими их выбирают в анкете. Значения едут на мост и совпадают с * перечнем `backend/domain/taxonomy.py`.
- отдаёт: GRADES, LANG_LEVELS, WORK_FORMATS, blankProfile, cvNote, fileSize, langRow, named, updatedNote

### state/progress.js (67)
- * Подпись начатого обхода, о котором ещё ничего не известно. * * Первая весть о ходе приходит не сразу: до неё полосы уже бегут, и подпись под * ними обязана сказать, чем именно бот занят.
- отдаёт: STARTING, bar, caption, rerunNote

### state/sections.js (33)
- * Разделы в том порядке, в каком они стоят в меню. Значок — лигатура шрифта * `Material Symbols Outlined`.
- отдаёт: CONTACTS_TABS, PROFILE_TABS, SECTIONS, SYSTEM_TABS

### state/settings.js (179)
- * Предел порога отбора. Дорожка ползунка размечена по нему, и он же * зажимает значение, приехавшее с моста.
- отдаёт: BOUNDS, SCORE_MAX, clampField, credsChanged, idleProbe, loginTrouble, matchingModels, mirrored, nextStep, probePill, sameCreds, scorePercent, sessionPill, sessionText, thresholdState

### state/skills.js (66)
- * Наибольший уровень навыка. Дорожка ползунка размечена по нему.
- отдаёт: aliasesAfter, countNote, grouped, levelPercent

### state/stats.js (209)
- * Сроки, за которые считают, — от короткого к длинному. * * `delta` — как называется прирост за этот срок. У «всего времени» его нет: * сравнивать не с чем, это и есть всё время.
- отдаёт: KPI, PERIODS, STATUS_ORDER, convNote, deltaNote, donut, duration, kpiRow, skillRows, skillRowsPerColumn, sliceTarget, statusColumns, weekBars

### state/statuses.js (13)
- * Статусы в том порядке, в каком их читают в кольце статистики. * * Значение совпадает с тем, каким статус приходит в строке списка и каким его * принимает смена статуса на мосту; им же покрашена точка рядом.
- отдаёт: STATUS_CHOICES

### state/vacancies.js (171)
- * Порядки списка в том виде, в каком их выбирают. Ключи уезжают на мост и * совпадают с перечнем `backend/repository/vacancies_list.VACANCY_SORTS`; * первый — тот, в котором список открывается.
- отдаёт: SORTS, ago, emptyNote, gradeLabel, remoteLabel, scoreTone, shortAgo, shownStack, sortKey, vacancyLine

### state/vacancy_actions.js (51)
- * Почему отправка и переразбор сейчас недоступны. * * Пустая фраза значит «доступно». Обе просьбы уходят боту, поэтому неживое * окружение запирает оба и объясняется теми же словами, что и кнопка обхода * внизу окна: две разные фразы об одной беде человек читает как две беды. * * Отклик уходит человеку, и без привязанного HR слать его некому; разбору же * HR не нужен — он его как раз и находит.
- отдаёт: actionBlocks, rawChips

### state/vacancy_card.js (160)
- * Своя запись правится, чужая читается: пояснение бота — след его работы, а не * заметка, и правка стирала бы то, по чему потом разбираются.
- отдаёт: timelineRows

### state/vacancy_filter.js (192)
- * Грейды объявлены анкетой: значения те же — и туда, и сюда они ездят через * мост, а второе их написание разошлось бы с первым молча.
- отдаёт: COMPANY_MAX, DATE_PRESETS, GRADE_CHOICES, HR_CHOICES, REMOTE_CHOICES, activeCount, blankFilter, filterPayload, pickNames

### state/wizard.js (147)
- * Экраны по порядку. Приветствие и финал — обложки: шага у них нет, и в * строке шагов они ничего не подсвечивают.
- отдаёт: PRESETS, backScreen, cvModes, cvReady, llmTrouble, nextScreen, presetFor, stepAt, stepMarks

### state/words.js (15)
- * Слово, согласованное с числом. * * «1 категории» человек читает как опечатку и перестаёт верить остальному на * экране. Числа 11–14 — исключение русского счёта и берут последнюю форму.
- отдаёт: plural

## styles — 76 файлов

### styles/accent-fill.css (16)
- Залито акцентом — так помечено выбранное и главное: основная кнопка окна, зажатая пилюля срока или рода, выбранный день в календаре. Одним правилом на три места, а не тремя одинаковыми: заливка здесь несёт один и тот же смысл «вот это», и разъедься её цвет или вес, соседние экраны стали бы помечать выбранное по-разному. Ввозится после оформления самих блоков: у их наведения та же весомость селектора, и выигрывает порядок.
- селекторы (1): .btn.primary,
.pill.active,
.date-day.selected
- берёт: --accent, --bg-primary

### styles/add-channel.css (29)
- Окно заведения канала: узкая коробка с шапкой, полем и подвалом. Сами шапка, тело и подвал — общие, в modal.css.
- селекторы (3): .add-channel, .add-channel .modal-body, .cnt-add-hint
- берёт: --text-tertiary

### styles/autosave-error.css (16)
- Отказ отложенной записи: коробка под формой вкладки анкеты. Стоит под формой, а не плашкой поверх экрана: анкету заполняют сверху вниз, и до последнего обязательного поля каждая запись законно отказана — плашка била бы на каждом поле. Рамкой и подложкой, а не голой строкой: строка под длинной формой теряется среди подписей полей.
- селекторы (1): .autosave-error
- берёт: --danger-border, --danger-wash, --err

### styles/base.css (75)
- Основание страницы: то, что верно на ней везде и не принадлежит ни одному блоку. Всё остальное оформление лежит файлом на блок рядом. Сюда попадает только то, у чего своего блока нет: сама страница, сброс чужих умолчаний и договор о шрифте — и текста, и значков.
- селекторы (6): *,
*::before,
*::after, html,
body, html, button, body, .material-symbols-outlined
- берёт: --bg-secondary, --text-primary

### styles/big-number.css (13)
- Крупное число: то, ради чего в карточку смотрят. Так набраны число в середине кольца статусов и числа плиток канала. Цифры моноширинные: числа стоят одно под другим и меняются на месте — пропорциональные дёргали бы соседей при каждом обновлении.
- селекторы (1): .big-num
- берёт: --text-primary

### styles/blacklist-dialog.css (164)
- Окно заведения строки отсева: выбор рода, значение с подсказчиком и причина. Шапка, тело и подвал — общие, в modal.css.
- селекторы (21): .bl-add-modal, .bl-add-modal .modal-body, .bl-kind-segmented, .bl-kind-seg, .bl-kind-seg:hover, .bl-kind-seg.active.keyword, .bl-kind-seg.active.hr, .bl-kind-seg.active.company, .bl-kind-seg.active.channel, .bl-modal-input,
.bl-modal-textarea, .bl-modal-input:focus,
.bl-modal-textarea:focus, .bl-modal-input::placeholder,
.bl-modal-textarea::placeholder, .bl-modal-textarea, .bl-combobox-wrap, .bl-combobox-dropdown, .bl-combobox-option, .bl-combobox-option:last-child, .bl-combobox-option:hover, .bl-combobox-option .opt-label, .bl-combobox-option .opt-sub, .bl-combobox-empty
- берёт: --accent, --bg-secondary, --bg-tertiary, --border, --fg-max, --kind-channel-active-bg, --kind-company-active-bg, --kind-hr-active-bg, --kind-keyword-active-bg, --selected-bg, --shadow-dropdown, --surface-raised, --text-primary, --text-secondary, --text-tertiary

### styles/blacklist.css (240)
- Чёрный список: полоса отбора и таблица строк под ней. Окно заведения строки — в blacklist-dialog.css.
- селекторы (34): .bl-toolbar, .bl-toolbar .search-box, .bl-toolbar .search-input, .bl-toolbar .search-box > .material-symbols-outlined, .bl-filter-pills, .bl-filter-pill, .bl-filter-pill .count, .bl-add-btn, .bl-add-btn:hover, .bl-add-btn .material-symbols-outlined, .bl-table, .bl-row, .bl-row:last-child, .bl-row.head, .bl-row.head .bl-active-head, .bl-row:hover:not(.head), .bl-row:not(.head) > .bl-kind-chip,
.bl-row:not(.head) > .bl-input.value,
.bl-row:not(.head) > .bl-when,
.bl-row:not(.head) > .icon-btn, .bl-row > .toggle, .bl-row:not(.head) > .toggle, .bl-row button.icon-btn:hover, .bl-kind-chip, .bl-kind-chip.keyword, .bl-kind-chip.hr, .bl-kind-chip.company, .bl-kind-chip.channel, .bl-input, .bl-input:hover, .bl-input:focus, .bl-input::placeholder, .bl-input.value, textarea.bl-input.reason, .bl-input.saved-flash, .bl-when, .bl-row.disabled .bl-input
- берёт: --accent, --accent-row-hover, --bg-secondary, --bg-tertiary, --border, --danger, --danger-tint, --info, --kind-channel-bg, --kind-channel-fg, --kind-company-bg, --kind-company-fg, --kind-hr-bg, --kind-keyword-bg, --kind-keyword-fg, --text-primary, --text-secondary, --text-tertiary

### styles/button.css (56)
- Кнопка с подписью. Значковые — в icon-button.css: у тех нет ни рамки, ни подложки, и общего с этими только сброс из base.css.
- селекторы (8): .btn, .btn:hover:not(:disabled), .btn.primary:hover:not(:disabled), .btn:disabled, .btn.danger, .btn.danger:hover:not(:disabled), .btn.text, .btn.text:hover:not(:disabled)
- берёт: --accent, --accent-hover-fill, --bg-tertiary, --border, --danger-btn, --err-btn-bg, --err-btn-bg-hover, --text-primary, --text-secondary

### styles/channel-stats.css (88)
- Числа канала: четыре плитки и полоса воронки под ними. Полосой, а не кольцом: доли здесь читают одну относительно другой — сколько из собранного дошло до отклика, — и в ряд это видно, а по кругу нет. Цвет отрезков — общий набор из status-color.css.
- селекторы (13): .ch-stats-grid, .ch-stat, .ch-stat-num.fit, .ch-stat-num.apply, .ch-stat-num.response, .ch-stat-label, .ch-bar, .ch-bar-seg, .ch-bar-legend, .ch-bar-legend .legend-item, .ch-bar-legend .status-dot, .ch-stats-empty, .ch-vacs-loading-more
- берёт: --accent, --bg-tertiary, --info, --status-applied, --text-secondary, --text-tertiary

### styles/chat.css (295)
- Переписка в карточке человека: лента писем, пузыри и строка отправки. Своим файлом, а не в оформлении карточки: карточку одевают три предмета, а переписка есть только у человека.
- селекторы (40): .cnt-chat-section, .cnt-chat-body, .cnt-chat-empty, .cnt-chat-day, .cnt-chat-older, .cnt-chat-older:hover, .cnt-bubble, .cnt-bubble.them, .cnt-bubble.me, .cnt-bubble.deleted, .cnt-bubble-content, .cnt-bubble-text, .cnt-bubble-text.deleted, .cnt-bubble-text.gone, .cnt-bubble-edited, .cnt-bubble-photo, .cnt-bubble-photo img, .cnt-bubble-doc, .cnt-bubble-doc:hover, .cnt-bubble-doc .material-symbols-outlined, .cnt-bubble-time, .cnt-bubble.me .cnt-bubble-time, .cnt-bubble-tick, .cnt-bubble-tick.read, .cnt-bubble.me .cnt-bubble-tick, .cnt-bubble.me .cnt-bubble-tick.read, .cnt-chat-input-area, .cnt-chat-input, .cnt-chat-input:focus, .cnt-chat-input::placeholder, .cnt-chat-input:disabled, .cnt-chat-attach, .cnt-chat-attach:hover:not(:disabled), .cnt-chat-attach:disabled, .cnt-chat-attach .material-symbols-outlined, .cnt-chat-send, .cnt-chat-send:hover:not(:disabled), .cnt-chat-send:disabled, .cnt-chat-send .material-symbols-outlined, .cnt-chat-disabled-hint
- берёт: --accent, --accent-chip-bg, --accent-muted, --bg-secondary, --bg-tertiary, --border, --surface-raised, --surface-raised-hover, --text-primary, --text-secondary, --text-tertiary

### styles/checkbox.css (15)
- Галочка с подписью в одну строку: подпись нажимается вместе с квадратиком.
- селекторы (2): .checkbox-row, .checkbox-row input
- берёт: --accent, --text-secondary

### styles/chips.css (70)
- Короткие подписи россыпью: синонимы навыка, стек места работы.
- селекторы (9): .chips, .chip, .chip-text, .chip-x, .chip:hover .chip-x, .chip-add, .chip-add:hover, .chip-input, .chip-input:focus
- берёт: --accent, --bg-secondary, --bg-tertiary, --border, --danger, --text-primary, --text-secondary, --text-tertiary

### styles/choice-row.css (78)
- Ряд вариантов выбора: два вида одного ряда. Сегментами — когда вариантов три-четыре и они делят ширину поровну; чипами — когда их одиннадцать и в один ряд равной ширины они не помещаются.
- селекторы (12): .choice-row, .choice, .choice:hover, .choice-row[data-look='seg'], .choice-row[data-look='seg'] .choice, .choice-row[data-look='seg'] .choice:first-child, .choice-row[data-look='seg'] .choice:last-child, .choice-row[data-look='seg'] .choice.active, .choice-row[data-look='seg'] .choice.active:hover, .choice-row[data-look='chip'], .choice-row[data-look='chip'] .choice, .choice-row[data-look='chip'] .choice.active
- берёт: --accent, --accent-chip-selected, --bg-primary, --border, --surface-hover-firm, --surface-raised, --text-primary, --text-secondary

### styles/collapse-arrow.css (21)
- Стрелка, которой сворачивают коробку: место работы и категорию навыков. Одним файлом на обе, а не по правилу в каждой коробке: знак у них один и тот же и поворачивается одинаково, а разъедься размер или скорость — две соседние вкладки анкеты сворачивались бы по-разному. Названа своим именем, а не «первым в шапке»: в шапке навыков стрелка обёрнута кнопкой, и отбор по месту клал бы набок кнопку вместо глифа — вместе с её отступами и мимо середины.
- селекторы (2): .collapse-arrow, .collapsed .collapse-arrow
- берёт: --text-secondary

### styles/collapsible.css (39)
- Коробка со сворачиваемой шапкой: категория навыков, место работы. Что внутри — своими файлами.
- селекторы (4): .collapsible, .collapsible-head, .new-cat, .new-cat:hover
- берёт: --accent, --bg-secondary, --bg-tertiary, --border, --text-tertiary

### styles/contact-block.css (58)
- Кружок и два имени рядом с ним: так подписаны HR и компания в карточке вакансии и кандидаты в подборщике привязки.
- селекторы (8): .contact-block, .hr-avatar, .hr-avatar .material-symbols-outlined, img.hr-avatar, .hr-info, .hr-name, .hr-name.muted, .hr-name.is-link:hover
- берёт: --accent, --bg-tertiary, --text-primary, --text-secondary, --text-tertiary

### styles/contact-card.css (152)
- Карточка контакта в правой панели: шапка, поля и коробки под ними. Одевает три карточки — человека, компании и канала: содержимое у них разное, а места этих мест одни. Переписка — в chat.css, мини-списки — в mini-list.css, числа канала — в channel-stats.css.
- селекторы (21): .cnt-det-head, .cnt-det-head > div, .cnt-det-head .hr-avatar, .cnt-det-name, .cnt-det-name.muted, .cnt-det-sub, .cnt-det-sub > *, .cnt-det-link, .cnt-det-link:hover, .cnt-det-meta-row, .cnt-det-meta-row > *, .cnt-det-meta-chip, .cnt-det-meta-chip.unread, .cnt-det-meta-chip.blacklist, .cnt-det-meta-chip .material-symbols-outlined, .cnt-form-grid, .cnt-input, .cnt-input:focus, .cnt-input::placeholder, .cnt-det-section, .cnt-vacs-empty
- берёт: --accent, --accent-chip-bg, --bg-secondary, --bg-tertiary, --border, --danger, --danger-tint-strong, --text-primary, --text-secondary, --text-tertiary

### styles/contacts-layout.css (77)
- Раскладка вкладки контактов: список слева, карточка справа. Панели прокручиваются раздельно и обе стоят на экране всегда: человека правят и пишут ему, не теряя из виду соседей по списку.
- селекторы (10): .cnt-list-toolbar, .cnt-list-toolbar .search-box, .cnt-list-toolbar .search-input, .cnt-list-toolbar .search-box > .material-symbols-outlined, .cnt-add-btn, .cnt-add-btn:hover, .cnt-add-btn .material-symbols-outlined, .cnt-list-empty, .cnt-detail-pane, .cnt-detail-empty
- берёт: --accent, --bg-primary, --bg-tertiary, --border, --selected-bg, --text-secondary, --text-tertiary

### styles/contacts.css (132)
- Строка списка контактов: кружок, имя с подписью и отметки в хвосте. Сами панели раздела — в contacts-layout.css, таблица отсева — в blacklist.css.
- селекторы (17): .cnt-hr-row, .cnt-hr-row:hover, .cnt-hr-row .hr-avatar, .cnt-hr-info, .cnt-hr-name, .cnt-hr-name.muted, .cnt-hr-sub, .cnt-hr-sub .at, .cnt-hr-sub .company, .cnt-hr-sub .muted, .cnt-hr-sub .sep, .cnt-hr-trailing, .cnt-hr-bl, .cnt-hr-bl .material-symbols-outlined, .cnt-hr-row.blacklisted .cnt-hr-name, .cnt-hr-unread, .cnt-co-count
- берёт: --accent, --accent-row-hover, --bg-primary, --bg-tertiary, --border, --danger, --text-primary, --text-secondary, --text-tertiary

### styles/cv-file.css (43)
- Файл резюме: пунктирная рамка — то же, чем обычно показывают «сюда кладут».
- селекторы (6): .pdf-row, .pdf-row > .material-symbols-outlined, .pdf-info, .pdf-name, .pdf-meta, .pdf-actions
- берёт: --bg-secondary, --border, --danger, --text-primary, --text-tertiary

### styles/date-picker.css (108)
- Поле даты и сетка месяца под ним.
- селекторы (16): .date-picker, .input-date-text, .input-date-text:hover:not(:disabled, :focus), .input-date-text:focus, .input-date-text.invalid, .date-panel, .date-panel.up, .date-head, .date-head .icon-btn:hover, .date-title, .date-week, .date-weekday, .date-cell, .date-day, .date-day:hover, .date-day.today
- берёт: --accent, --bg-secondary, --bg-tertiary, --border, --err, --scrim, --selected-bg, --text-primary, --text-secondary

### styles/donut.css (45)
- Кольцо долей: обводка круга сегментами и число в середине.
- селекторы (5): .donut-wrap, .donut, .donut-part, .donut-center, .donut-label
- берёт: --text-tertiary

### styles/dropdown.css (67)
- Выпадающий список со своим видом: системный в тёмном окне светлая заплата.
- селекторы (8): .cdd, .cdd-btn, .cdd-btn:hover,
.cdd.open .cdd-btn, .cdd-btn .material-symbols-outlined, .cdd-panel, .cdd-option, .cdd-option:hover, .cdd-option.active
- берёт: --accent, --bg-secondary, --border, --selected-bg, --shadow-dropdown, --text-primary, --text-secondary, --text-tertiary

### styles/empty-note.css (9)
- Надпись на месте пустого списка: почему здесь ничего нет. Одна на все экраны — журнал, настройки и те, что приедут следом.
- селекторы (1): .empty-note
- берёт: --text-tertiary

### styles/experience.css (365)
- Место работы: коробка карточки, шапка и всё, что внутри. Коробка своя, не общая с категорией навыков: там шапку нажимает одна стрелка, а здесь — вся строка целиком, и разложена она сеткой под стрелку, подпись и корзину.
- селекторы (48): .exp-card, .exp-header, .exp-card.collapsed .exp-header, .exp-summary, .exp-summary > strong, .exp-summary > .role, .exp-summary .period, .exp-delete, .exp-delete:hover, .exp-delete .material-symbols-outlined, .exp-body, .field-row, .field-row .span-2,
.field-row .input.span-2,
.field-row .date-pair.span-2, .field-label, .field-row .input, .date-pair, .date-pair .date-picker, .date-dash, .date-current, .date-current input, .list-block .field-label, .list-add, .list-add:hover, .list-add .material-symbols-outlined, .list-item, .list-bullet, .list-input, .list-input:hover, .list-input:focus, .list-item .icon-btn, .list-item .icon-btn .material-symbols-outlined, .list-item:hover .icon-btn, .list-item button.icon-btn:hover, .skills-block, .skill-picker, .skill-picker-search, .skill-picker-search .material-symbols-outlined, .skill-picker-search input, .skill-picker-list, .skill-picker-cat, .skill-picker-item, .skill-picker-item:hover, .skill-picker-item.disabled, .skill-picker-item.disabled:hover, .skill-picker-item .lvl, .skill-picker-empty, .new-exp, .new-exp:hover
- берёт: --accent, --bg-secondary, --bg-tertiary, --border, --danger, --danger-tint, --selected-bg, --shadow-dropdown, --text-primary, --text-secondary, --text-tertiary

### styles/filter-group.css (18)
- Группа отбора: подпись над своими полями и черта под ними.
- селекторы (3): .filter-group, .filter-group:last-child, .filter-label
- берёт: --border, --text-tertiary

### styles/footer.css (40)
- Рама нижней полосы: три её места и то, как они делят ширину. Что стоит внутри — лампочки, режим, ход обхода, счётчик — своими файлами.
- селекторы (4): .bottom-bar, .bb-left, .bb-right, .bb-center
- берёт: --bg-secondary, --border

### styles/health-lamp.css (34)
- Лампочка состояния: точка и короткое имя под ней.
- селекторы (5): .health, .health .dot, .health[data-state='ok'] .dot, .health[data-state='err'] .dot, .health-label
- берёт: --accent, --accent-glow-inner, --accent-glow-outer, --err, --err-glow-inner, --err-glow-outer, --text-secondary, --text-tertiary

### styles/icon-button.css (34)
- Кнопка-значок: квадрат со значком внутри, без подписи. Вынесена на втором потребителе — кнопка обхода в полосе и очистка журнала.
- селекторы (5): .icon-btn, .icon-btn .material-symbols-outlined, .icon-btn:hover, .icon-btn.is-disabled, .icon-btn.is-disabled:hover
- берёт: --bg-tertiary, --text-primary, --text-secondary

### styles/input.css (57)
- Поле ввода, многострочное поле и поле для секрета рядом с глазом. Экран настроек уменьшает их своим правилом — там полей вдвое больше.
- селекторы (8): .input,
.textarea, .input:hover:not(:disabled, :focus),
.textarea:hover:not(:disabled, :focus), .input:focus,
.textarea:focus, .input::placeholder,
.textarea::placeholder, .textarea, .secret-input, .secret-input .input, .input.mono
- берёт: --accent, --bg-secondary, --border, --text-primary, --text-secondary, --text-tertiary

### styles/lang-rows.css (49)
- Языки анкеты: строка на язык и кнопка добавления под списком.
- селекторы (8): .lang-list, .lang-row, .lang-row .input, .lang-row .cdd-label,
.lang-row .cdd-option, .lang-remove, .lang-remove:hover, .lang-add, .lang-add:hover
- берёт: --accent, --danger, --text-secondary, --text-tertiary

### styles/log-level-pill.css (67)
- Пилюля уровня: значок, имя и счёт записей этого уровня во всём буфере. Цвет зажатой берётся по тону, и тон тот же, что у уровня в строке списка (`log-row.css`): разойдись они, красная строка стояла бы под жёлтой пилюлей.
- селекторы (10): .logs-level-pill, .logs-level-pill .material-symbols-outlined, .logs-level-pill:hover, .logs-level-pill .count, .logs-level-pill.active .material-symbols-outlined, .logs-level-pill.active .count, .logs-level-pill.active[data-tone='error'], .logs-level-pill.active[data-tone='warn'], .logs-level-pill.active[data-tone='info'], .logs-level-pill.active[data-tone='debug']
- берёт: --accent, --alert-fill, --alert-muted, --alert-text, --bg-secondary, --bg-tertiary, --border, --danger, --err-fill, --err-muted, --info, --info-fill, --info-muted, --text-primary, --text-secondary, --text-tertiary

### styles/log-row.css (67)
- Строка журнала: время, уровень, источник, сообщение — и трассировка под ними, когда строку развернули.
- селекторы (13): .logs-row, .logs-row:hover, .logs-row.expanded, .logs-time, .logs-level, .logs-level[data-tone='error'], .logs-level[data-tone='warn'], .logs-level[data-tone='info'], .logs-level[data-tone='debug'], .logs-source, .logs-msg, .logs-row.expanded .logs-msg, .logs-details
- берёт: --accent-row-hover, --alert-text, --bg-secondary, --bg-tertiary, --border, --danger, --info, --text-primary, --text-secondary, --text-tertiary

### styles/logs.css (39)
- Экран журнала: панель сверху и список записей под ней. Что стоит внутри — пилюли и строки — своими файлами.
- селекторы (5): .logs-toolbar, .logs-level-pills, .logs-toolbar-gap, .logs-auto-refresh, .logs-list

### styles/master-detail.css (53)
- Каркас «список слева, подробности справа» — общий у контактов и вакансий. Своим файлом, потому что раскладка одна на два раздела, а написана была дважды: под приставкой `cnt-` и под `vac-`. Ширина панели стояла двумя числами в двух файлах, и разъехались бы они молча — а разделы эти стоят соседними вкладками одного окна, и разницу видно глазом. Селекторы сгруппированы, а не сведены к общему имени: имена классов несущие — по ним разметка и оформление раздела ищутся поиском, — и переименование стоило бы дороже, чем даёт. Что осталось у каждого раздела своим: подложка подробностей (у вакансий отступы плотнее — строка там гуще), пустые состояния (у вакансий это центрованный столбик со значком, у контактов простой абзац) и всё содержимое строки.
- селекторы (4): .cnt-layout,
.vacancies-layout, .cnt-list-pane,
.vac-list-pane, .cnt-list,
.vac-list, .cnt-hr-row.selected,
.vac-row.selected
- берёт: --accent, --bg-secondary, --border, --selected-bg

### styles/menu.css (72)
- Меню действий: что стоит внутри списка под кнопкой-значком. Оправа окошка — общая, в popover.css.
- селекторы (11): .menu, .menu-item, .menu-item:hover, .menu-item .material-symbols-outlined, .menu-item.blocked,
.menu-item.blocked .material-symbols-outlined, .menu-item.blocked, .menu-item.blocked:hover, .menu-item.danger,
.menu-item.danger .material-symbols-outlined, .menu-item.danger:hover, .menu-item.danger:hover,
.menu-item.danger:hover .material-symbols-outlined, .menu-line
- берёт: --border, --danger, --danger-hover-fg, --danger-tint, --selected-bg, --text-primary, --text-secondary, --text-tertiary

### styles/mini-list.css (96)
- Нажимаемая строка внутри карточки контакта: вакансия и человек компании. Обе ведут отсюда наружу — к вакансии и к карточке человека, — и поэтому одеты одинаково: подсветка при наведении и имя, загорающееся акцентом, говорят, что по строке нажимают. Коробка вокруг них общая, в contact-card.css.
- селекторы (12): .vacs-mini,
.hrs-mini, .vac-mini-row, .hr-mini-row, .vac-mini-row:first-child,
.hr-mini-row:first-child, .vac-mini-row:hover,
.hr-mini-row:hover, .vac-mini-row:hover .vac-mini-title,
.hr-mini-row:hover .hr-mini-name, .vac-mini-score, .vac-mini-title,
.hr-mini-name, .vac-mini-when, .hr-mini-row .hr-avatar, .hr-mini-meta, .hr-mini-go
- берёт: --accent, --bg-tertiary, --border, --selected-bg, --text-primary, --text-tertiary

### styles/modal.css (147)
- Окно поверх окна: затемнение на весь экран и коробка по центру.
- селекторы (19): .modal-backdrop, .modal-dialog, .modal-message, .modal-title, .modal-title .material-symbols-outlined, .modal-head, .modal-head .modal-title, .modal-head > .material-symbols-outlined, .modal-title-meta, .modal-close, .modal-close:hover, .modal-close .material-symbols-outlined, .modal-body, .modal-footer, .modal-footer .btn, .modal-footer .btn .material-symbols-outlined, .modal-subtitle, .modal-error, .modal-actions
- берёт: --bg-secondary, --bg-tertiary, --border, --danger, --scrim, --shadow-modal, --text-primary, --text-secondary, --text-tertiary

### styles/mode.css (54)
- Переключатель режима бота: слово, дорожка и бегунок на ней.
- селекторы (14): .mode-control, .mode-text, .mode-track, .mode-knob, .mode-control[data-mode='Off'] .mode-knob, .mode-control[data-mode='Off'] .mode-text, .mode-control[data-mode='Off'] .mode-track, .mode-control[data-mode='DM Only'] .mode-knob, .mode-control[data-mode='DM Only'] .mode-text, .mode-control[data-mode='DM Only'] .mode-track, .mode-control[data-mode='Full'] .mode-knob, .mode-control[data-mode='Full'] .mode-text, .mode-control[data-mode='Full'] .mode-track, .mode-control.is-disabled
- берёт: --accent, --accent-muted, --bg-tertiary, --border, --err, --err-muted, --text-secondary, --text-tertiary, --warn, --warn-muted

### styles/nav.css (94)
- Боковое меню: разделы и кнопка разворота.
- селекторы (14): .sidebar, .nav-group,
.sidebar-toggle, .nav-group, .nav-icon-rail, .nav-icon-rail .material-symbols-outlined, .nav-label, .app-frame:not(.sidebar-expanded) .nav-label, .nav-group:hover, .nav-group.active, .nav-group.active .nav-icon-rail .material-symbols-outlined, .sidebar-spacer, .sidebar-toggle, .sidebar-toggle:hover, .sidebar-toggle .material-symbols-outlined
- берёт: --accent, --bg-tertiary, --border, --rail-w, --selected-bg, --text-primary, --text-secondary, --text-tertiary

### styles/notes-area.css (33)
- Заметка к вакансии и вспышка «записано». Вспышка тут же, а не в оформлении заметки: ею отзывается и пояснение в ленте, а правило у неё одно — зелёная рамка с ореолом на те же доли секунды.
- селекторы (3): .notes-area, .notes-area:focus, .saved-flash,
.saved-flash:focus
- берёт: --accent, --accent-flash, --accent-focus-ring, --bg-tertiary, --border, --text-primary

### styles/palette.css (195)
- Палитра приложения: единственное место, где цвет записан значением, — всё остальное оформление берёт его через var(), и это держит хук. Собрана сплошным вычитыванием обоих <style> прежней разметки (`main.html` и `wizard.html`, снесены слайсом В1): 237 записей литералами, 104 различных цвета. Оттенки не сведены и не подправлены — близкие, но разные пары оставлены разными, потому что разницу видно на экране.
- селекторы (1): :root
- объявляет: --accent, --accent-badge-hover, --accent-chip-bg, --accent-chip-selected, --accent-flash, --accent-focus-ring, --accent-glow-inner, --accent-glow-outer, --accent-hover-faint, --accent-hover-fill, --accent-hover-soft, --accent-muted, --accent-option-active, --accent-row-current, --accent-row-hover, --alert, --alert-card-bg, --alert-card-border, --alert-fill, --alert-muted, --alert-text, --bg-over-content, --bg-primary, --bg-secondary, --bg-tertiary, --border, --danger, --danger-border, --danger-btn, --danger-hover-fg, --danger-tint, --danger-tint-strong, --danger-toast-bg, --danger-toast-fg, --danger-wash, --dot-outline, --err, --err-btn-bg, --err-btn-bg-hover, --err-fill, --err-fill-strong, --err-glow-inner, --err-glow-outer, --err-muted, --err-stop-hover, --err-zone-bg, --err-zone-border, --fg-max, --info, --info-card-bg, --info-card-border, --info-fill, --info-muted, --kind-channel-active-bg, --kind-channel-bg, --kind-channel-fg, --kind-company-active-bg, --kind-company-bg, --kind-company-fg, --kind-hr-active-bg, --kind-hr-bg, --kind-keyword-active-bg, --kind-keyword-bg, --kind-keyword-fg, --ok, --ok-fill, --ok-text, --score-warn, --scrim, --selected-bg, --shadow-dropdown, --shadow-modal, --shadow-popup, --shadow-soft, --stats-group-funnel, --stats-group-ingest, --stats-group-outcome, --status-applied, --status-not-fit, --status-not-fit-timeline, --status-offer, --status-test, --surface-hover-firm, --surface-raised, --surface-raised-hover, --text-primary, --text-secondary, --text-tertiary, --tl-halo-answered, --tl-halo-applied, --tl-halo-decline, --tl-halo-default, --tl-halo-ghosting, --tl-halo-in-progress, --tl-halo-invitation, --tl-halo-new, --tl-halo-not-fit, --tl-halo-offer, --tl-halo-scam, --tl-halo-test, --warn, --warn-glow-inner, --warn-glow-outer, --warn-muted

### styles/pick-list.css (58)
- Выбор многих из длинного перечня: кнопка со счётом и раскрывающаяся панель с поиском под ней. Выпадающий список одного значения — в dropdown.css.
- селекторы (7): .pick, .pick-btn, .pick-btn .material-symbols-outlined, .pick-panel, .pick-list, .pick-list .checkbox-row, .pick-list .empty-note
- берёт: --bg-tertiary, --border, --shadow-dropdown, --text-primary, --text-tertiary

### styles/picker.css (162)
- Окно выбора: полоса поиска, список кандидатов и строка заведения под ним. Шапка, тело и подвал — общие, в modal.css; кружок с именами — в contact-block.css.
- селекторы (23): .vac-picker-modal, .picker-search-bar, .picker-search-bar .material-symbols-outlined, .picker-search-bar input, .picker-search-bar input:focus, .picker-list, .picker-empty, .picker-row, .picker-row:hover, .picker-row.selected, .picker-row.current, .picker-row.current .picker-name, .picker-row.blocked, .picker-info, .picker-name, .picker-current-mark, .picker-sub, .picker-meta, .vac-count, .picker-create, .picker-create-toggle, .picker-create-toggle:hover, .picker-create-toggle .material-symbols-outlined
- берёт: --accent, --accent-hover-faint, --accent-row-current, --accent-row-hover, --bg-tertiary, --border, --selected-bg, --text-primary, --text-secondary, --text-tertiary

### styles/pill.css (20)
- Пилюля выбора: нажимаемая скобка, одна из ряда. Ею выбирают род строки в чёрном списке и срок в статистике. Выбранная залита акцентом целиком, а не подсвечена рамкой: пилюль в ряду пять, и приглушённой отметки среди них глаз не находит.
- селекторы (2): .pill, .pill:hover
- берёт: --accent, --bg-secondary, --border, --text-secondary

### styles/pipeline.css (80)
- Пороги отбора: пять величин в ряд, ползунок, числовые поля и тумблер.
- селекторы (11): .pipeline-row, .pipeline-row > div, .pipeline-label, .with-unit, .with-unit .input, .with-unit .unit, .slider-row, .slider-num, .slider-row:hover input[type='range'].slider::-webkit-slider-thumb, .slider-row:hover input[type='range'].slider::-moz-range-thumb, .with-toggle
- берёт: --text-secondary, --text-tertiary

### styles/plaque.css (36)
- Плашка отказа: одна на всё окно, поверх чего угодно.
- селекторы (3): .app-toast, .app-toast.visible, .app-toast.danger
- берёт: --bg-secondary, --border, --danger, --danger-toast-bg, --danger-toast-fg, --shadow-soft, --text-primary

### styles/popover.css (19)
- Окошко под кнопкой: общая оправа всплывающих панелей. Своё у каждой — сторона, к которой она прижата, ширина и то, что внутри; общее — то, чем она отделена от страницы под собой.
- селекторы (2): .pop-wrap, .pop
- берёт: --bg-secondary, --border, --shadow-popup

### styles/progress.css (61)
- Ход обхода: две полосы и подпись рядом с ними.
- селекторы (7): .bb-center .progress-wrap, .progress-bars, .progress-caption, .progress-bar, .progress-fill, .progress-bar[data-indeterminate='true'] .progress-fill, @keyframes slide
- берёт: --accent, --bg-tertiary, --text-secondary

### styles/raw-text.css (87)
- Окно исходного текста: полоса сведений об объявлении и сам текст под ней. Шапка, тело и крестик — общие, в modal.css.
- селекторы (9): .vac-raw-modal, .raw-meta, .raw-meta-chip, .raw-meta-chip .material-symbols-outlined, .raw-copy-btn, .raw-copy-btn:hover, .raw-copy-btn:active, .raw-copy-btn .material-symbols-outlined, .raw-text
- берёт: --accent, --bg-over-content, --bg-secondary, --bg-tertiary, --border, --text-primary, --text-secondary

### styles/ruled-row.css (11)
- Строка перечня, отделённая чертой сверху: строка навыка в анкете и строка навыка в карточке статистики. Общее у них — сетка, выравнивание по средней линии и сама черта; колонки, зазор, отступ и размер шрифта у каждой свои: одну правят, вторую читают.
- селекторы (1): .ruled-row
- берёт: --border

### styles/run.css (26)
- Кнопка обхода: пуск и остановка одним значком. Общее с прочими кнопками-значками — в icon-button.css.
- селекторы (3): .run-btn::before, .run-btn[data-running='true']::before, .run-btn[data-running='true']:hover
- берёт: --err, --err-stop-hover, --ok

### styles/screen.css (51)
- Общее у экранов раздела: шапка с заголовком и поле под вкладками.
- селекторы (8): .screen-body, .screen-body.flush, .page-head, .page-title, .page-title-meta, .updated-ts, .form-grid, .form-grid .span-2
- берёт: --text-primary, --text-tertiary

### styles/search-box.css (56)
- Строка поиска над списком: лупа, поле и крестик очистки. Своим файлом, а не в оформлении списка: коробка одна на все списки окна — вакансии и четыре вкладки контактов, — и различает их только полоса, в которой она стоит.
- селекторы (7): .search-box, .search-box .material-symbols-outlined, .search-input, .search-input:focus, .search-clear, .search-clear:hover, .search-clear .material-symbols-outlined
- берёт: --surface-hover-firm, --text-primary, --text-secondary, --text-tertiary

### styles/settings-section.css (63)
- Коробка с заголовком-шапкой: секция настроек, карточка статистики. Имя осталось от первого потребителя — переименование задело бы три файла ради одного слова.
- селекторы (9): .settings-section, .settings-section-title, .settings-section-title .material-symbols-outlined, .settings-section.danger, .settings-section.danger .settings-section-title,
.settings-section.danger .settings-section-title .material-symbols-outlined, .danger-row, .danger-text, .danger-sub, .danger-row .btn
- берёт: --bg-secondary, --border, --danger, --err-zone-bg, --err-zone-border, --text-primary, --text-secondary, --text-tertiary

### styles/settings.css (104)
- Экран настроек: колонка секций посреди поля. Что внутри секций — сетка полей, пороги, опасная зона — своими файлами.
- селекторы (14): .settings-page, .settings-inner, .settings-page .input, .settings-page .btn, .settings-page .btn .material-symbols-outlined, .settings-page .btn.danger, .settings-page .btn.danger:hover:not(:disabled), .settings-row.spaced, .settings-row, .settings-row .span-2, .settings-actions, .session-actions, .session-row, .session-info
- берёт: --bg-tertiary, --border, --danger, --text-tertiary

### styles/shell.css (42)
- Рама окна: боковое меню, поле раздела, нижняя полоса. Раскладка сеткой, и разворот меню — это правка одной её переменной.
- селекторы (4): .app-frame, .app-frame.sidebar-expanded, .main, .placeholder-content
- объявляет: --footer-h, --rail-w, --sidebar-w
- берёт: --bg-primary, --bg-secondary, --footer-h, --rail-w, --sidebar-w, --text-tertiary

### styles/skills.css (145)
- Навыки: строка навыка внутри категории. Сама коробка категории — общая, в collapsible.css.
- селекторы (21): .cat-name, .cat-name:hover, .cat-name:focus, .cat-spacer, .cat-add, .cat-add:hover, .cat-add .material-symbols-outlined, .cat-delete, .cat-delete:hover, .cat-delete .material-symbols-outlined, .skill-row, .skill-row:hover, .skill-row .icon-btn:hover, .skill-row .icon-btn .material-symbols-outlined, .skill-row:hover input[type='range'].slider::-webkit-slider-thumb, .skill-row:hover input[type='range'].slider::-moz-range-thumb, .skill-name, .skill-name:hover, .skill-name:focus, .level, .level-num
- берёт: --accent, --accent-row-hover, --bg-secondary, --border, --danger, --danger-tint, --text-primary, --text-secondary, --text-tertiary

### styles/slider.css (71)
- Ползунок: порог отбора в настройках, уровень навыка в анкете. Заливка дорожки нарисована фоном самого поля: у ползунка нет своей «пройденной» части, а два элемента поверх друг друга разъезжались бы на краях. Долю кладёт разметка переменной `--pct`.
- селекторы (7): input[type='range'].slider, input[type='range'].slider::-webkit-slider-runnable-track, input[type='range'].slider::-moz-range-track, input[type='range'].slider::-webkit-slider-thumb, input[type='range'].slider::-moz-range-thumb, input[type='range'].slider:active::-webkit-slider-thumb, input[type='range'].slider:active::-moz-range-thumb
- берёт: --accent, --bg-tertiary, --pct

### styles/stats-channels.css (136)
- Карточка «Каналы»: воронка канала одиннадцатью колонками. Сеткой, а не таблицей: имя канала и колонки конверсии резиновые, числовые — узкие по содержимому, и только так все одиннадцать влезают в карточку без поперечной прокрутки. Группы «Ингест», «Воронка отклика» и «Конверсия» отделены тонкой чертой — без неё одиннадцать чисел читаются как один ряд.
- селекторы (23): .stats-ch-grid, .stats-ch-grid > *, .stats-ch-grid .stats-ch-group, .stats-ch-grid .stats-ch-group.ingest, .stats-ch-grid .stats-ch-group.funnel, .stats-ch-grid .stats-ch-group.outcome, .stats-ch-grid .stats-ch-th, .stats-ch-grid .stats-ch-name-cell, .stats-ch-grid .stats-ch-th-name, .stats-ch-grid .stats-ch-sep-l, .stats-ch-grid .stats-ch-conv, .stats-ch-grid .stats-ch-conv-label, .stats-ch-grid .stats-ch-conv-meter, .stats-ch-grid .stats-ch-conv-meter-fill, .stats-ch-grid .stats-ch-row, .stats-ch-grid .stats-ch-row.is-hover, .stats-ch-grid .v-dim, .stats-ch-grid .v-fit, .stats-ch-grid .v-sent, .stats-ch-grid .v-answ, .stats-ch-grid .v-invite, .stats-ch-grid .v-decline, .stats-ch-grid .stats-ch-last
- берёт: --accent, --bg-tertiary, --border, --err, --info, --stats-group-funnel, --stats-group-ingest, --stats-group-outcome, --status-applied, --surface-raised, --text-primary, --text-secondary, --text-tertiary

### styles/stats-responses.css (84)
- Карточка «Ответы HR»: столбцы по дням недели и две метрики под ними. Столбцы сверху, метрики снизу за чертой: график — то, ради чего в карточку смотрят, а метрики его подписывают.
- селекторы (11): .stats-resp-card, .stats-resp-chart, .stats-resp-bar-wrap, .stats-resp-bar-num, .stats-resp-bar, .stats-resp-bar.weekend, .stats-resp-bar-label, .stats-resp-stats, .stats-resp-stat-num, .stats-resp-stat-num.dim, .stats-resp-stat-label
- берёт: --accent, --alert, --border, --text-primary, --text-secondary, --text-tertiary

### styles/stats-skills.css (109)
- Карточка «Скилы»: навыки вакансий тремя колонками с полосой частоты. Полоса, а не одно число: по ней видно, во сколько раз первый навык встречается чаще пятого, — а это и есть то, ради чего в карточку смотрят.
- селекторы (16): .stats-skills-grid, .stats-skill-row, .stats-skill-row.first-in-col, .stats-skill-check, .stats-skill-name, .stats-skill-row:not(.mine) .stats-skill-name, .stats-skill-bar, .stats-skill-bar-fill, .stats-skill-row.mine .stats-skill-bar-fill, .stats-skill-row:not(.mine) .stats-skill-bar-fill, .stats-skill-num, .stats-skills-legend, .stats-skills-legend span, .stats-skills-legend .leg-dot, .stats-skills-legend .leg-mine, .stats-skills-legend .leg-other
- берёт: --accent, --bg-tertiary, --border, --text-primary, --text-secondary, --text-tertiary

### styles/stats-status.css (55)
- Карточка «Статусы»: счётчики двумя колонками и кольцо между ними. Само кольцо — в donut.css, цвет точки — в status-color.css.
- селекторы (7): .stats-status-card, .stats-status-col, .stats-status-col.right, .stats-sc-item, .stats-sc-item:hover, .stats-sc-name, .stats-sc-num
- берёт: --bg-tertiary, --text-primary, --text-secondary

### styles/stats.css (157)
- Статистика: полоса срока, сетка карточек и сама коробка карточки. Что стоит внутри карточек — своими файлами.
- селекторы (25): .stats-toolbar, .stats-period-pill, .stats-refresh-btn, .stats-refresh-btn:hover, .stats-refresh-btn .material-symbols-outlined, .stats-refresh-btn.spinning .material-symbols-outlined, @keyframes stats-refresh-spin, .stats-grid, .stats-card, .stats-card-title, .stats-col-6, .stats-col-12, .stats-loading, .stats-kpi-row, .stats-kpi-row .stats-card, .stats-kpi, .stats-kpi-num, .stats-kpi-num[data-tone='applied'], .stats-kpi-num[data-tone='progress'], .stats-kpi-num[data-tone='offer'], .stats-kpi-num[data-tone='decline'], .stats-kpi-label, .stats-kpi-delta, .stats-kpi-delta[data-tone='up'], .status-dot
- берёт: --accent, --bg-secondary, --border, --err, --ok, --status-applied, --status-offer, --text-primary, --text-secondary, --text-tertiary

### styles/status-color.css (50)
- Цвет статуса вакансии — один набор на всё окно. Красит три места: сегмент кольца, точку в списке рядом с ним и отрезок полосы воронки в карточке канала. Разойдись они, одна и та же ступень воронки была бы разного цвета на соседних экранах. Обводка и заливка названы вместе: у кольца цвет несёт stroke, у точки и отрезка — background.
- селекторы (11): .donut-part[data-status='New'],
.status-dot[data-status='New'],
.ch-bar-seg[data-status='New'], .donut-part[data-status='Applied'],
.status-dot[data-status='Applied'],
.ch-bar-seg[data-status='Applied'], .donut-part[data-status='Answered'],
.status-dot[data-status='Answered'],
.ch-bar-seg[data-status='Answered'], .donut-part[data-status='Test'],
.status-dot[data-status='Test'],
.ch-bar-seg[data-status='Test'], .donut-part[data-status='Invitation'],
.status-dot[data-status='Invitation'],
.ch-bar-seg[data-status='Invitation'], .donut-part[data-status='In Progress'],
.status-dot[data-status='In Progress'],
.ch-bar-seg[data-status='In Progress'], .donut-part[data-status='Offer'],
.status-dot[data-status='Offer'],
.ch-bar-seg[data-status='Offer'], .donut-part[data-status='Decline'],
.status-dot[data-status='Decline'],
.ch-bar-seg[data-status='Decline'], .donut-part[data-status='Ghosting'],
.status-dot[data-status='Ghosting'],
.ch-bar-seg[data-status='Ghosting'], .donut-part[data-status='Scam'],
.status-dot[data-status='Scam'],
.ch-bar-seg[data-status='Scam'], .donut-part[data-status='Not Fit'],
.status-dot[data-status='Not Fit'],
.ch-bar-seg[data-status='Not Fit']
- берёт: --accent, --alert, --err, --fg-max, --info, --ok, --status-applied, --status-not-fit, --status-offer, --status-test, --warn

### styles/status-picker.css (69)
- Выбор статуса: что стоит внутри окошка под значком статуса. Оправа окошка — общая, в popover.css.
- селекторы (9): .status-picker, .status-options, .status-option, .status-option:hover, .status-option input, .popover-comment, .popover-comment:focus, .popover-actions, .popover-actions .btn
- берёт: --accent, --bg-tertiary, --border, --selected-bg, --text-primary

### styles/status-pill.css (21)
- Плашка состояния в шапке секции: прижата к правому краю.
- селекторы (3): .status-pill, .status-pill[data-tone='ok'], .status-pill[data-tone='err']
- берёт: --danger, --err-fill-strong, --ok-fill, --ok-text

### styles/tabs.css (28)
- Верхние вкладки раздела: одна строка над содержимым экрана.
- селекторы (4): .top-tabs, .top-tabs .tab, .top-tabs .tab:hover, .top-tabs .tab.active
- берёт: --accent, --bg-secondary, --border, --text-primary, --text-secondary

### styles/tg-login.css (42)
- Окно входа в Telegram — своё, а не общее окно-вопрос. Отличия не в украшении: коробка у́же и без тени, потому что спрашивает одно короткое поле, а поле в ней темнее подложки — на общем цвете оно совпадает с коробкой, и человеку не видно, куда набирать код.
- селекторы (5): .tg-login, .tg-login-box, .tg-login .modal-title, .tg-login .input, .tg-login .modal-actions
- берёт: --bg-secondary, --bg-tertiary, --border

### styles/timeline.css (162)
- Лента жизни вакансии: точка, текст и время в три колонки.
- селекторы (27): .timeline, .tl-item, .tl-item .status-dot, .tl-item .status-dot[data-status=''], .tl-item .status-dot[data-status='Not Fit'], .tl-item.current .status-dot, .tl-item.current .status-dot[data-status='New'], .tl-item.current .status-dot[data-status='Applied'], .tl-item.current .status-dot[data-status='Answered'], .tl-item.current .status-dot[data-status='Test'], .tl-item.current .status-dot[data-status='Invitation'], .tl-item.current .status-dot[data-status='In Progress'], .tl-item.current .status-dot[data-status='Offer'], .tl-item.current .status-dot[data-status='Decline'], .tl-item.current .status-dot[data-status='Ghosting'], .tl-item.current .status-dot[data-status='Scam'], .tl-item.current .status-dot[data-status='Not Fit'], .tl-text, .tl-label, .tl-history-row, .tl-history-row .tl-label, .tl-event, .tl-note, .tl-note:hover, .tl-note:focus, .tl-note::placeholder, .tl-when
- берёт: --accent, --bg-tertiary, --border, --dot-outline, --status-not-fit-timeline, --text-primary, --text-secondary, --text-tertiary, --tl-halo-answered, --tl-halo-applied, --tl-halo-decline, --tl-halo-default, --tl-halo-ghosting, --tl-halo-in-progress, --tl-halo-invitation, --tl-halo-new, --tl-halo-not-fit, --tl-halo-offer, --tl-halo-scam, --tl-halo-test

### styles/toggle.css (64)
- Переключатель-пилюля: дорожка и шарик на ней. Двух размеров, и размер несущий: в анкете порогов он стоит один в колонке и взят в полный рост, а в строке списка контактов делит место с именем, счётом и значком отсева — там он вдвое меньше. Числа лежат переменными, чтобы шарик не пришлось пересчитывать на каждый размер руками.
- селекторы (7): .toggle, .toggle.compact, .toggle::after, .toggle:checked, .toggle:checked::after, .toggle:disabled, .toggle.locked:disabled
- объявляет: --toggle-gap, --toggle-h, --toggle-knob, --toggle-w
- берёт: --accent, --bg-primary, --bg-tertiary, --text-tertiary, --toggle-gap, --toggle-h, --toggle-knob, --toggle-w

### styles/unread.css (110)
- Счёт непрочитанного: пилюля со значком письма и список под ней.
- селекторы (15): .badge-unread, .badge-unread .material-symbols-outlined, .badge-unread[data-has-unread='true'], .badge-unread:hover, .badge-unread[data-has-unread='true']:hover, .unread-popup-backdrop, .unread-popup, .unread-popup-empty, .unread-popup-list, .unread-popup-row, .unread-popup-row:last-child, .unread-popup-row:hover, .unread-popup-name, .unread-popup-sub, .unread-popup-count
- берёт: --accent, --accent-badge-hover, --bg-secondary, --border, --selected-bg, --shadow-popup, --surface-raised, --surface-raised-hover, --text-primary, --text-tertiary

### styles/vacancies.css (199)
- Экран вакансий: список слева, подробности справа, строка в три этажа.
- селекторы (27): .vac-list-toolbar, .vac-list-toolbar .icon-btn, .vac-list-toolbar .icon-btn .material-symbols-outlined, .vac-list-toolbar .icon-btn:hover, .vac-sort-menu, .vac-sort-option, .vac-sort-option:hover, .vac-sort-option.active, .vac-list-empty, .vac-list-empty .material-symbols-outlined, .vac-detail-pane, .vac-detail-empty, .vac-row, .vac-row:hover, .vac-row-head, .vac-title, .vac-meta, .vac-meta .v-co, .vac-meta .sep, .vac-meta .when, .vac-score, .vac-score[data-tone='warn'], .vac-score[data-tone='bad'], .vac-stack, .mini-chip, .mini-chip.more, .mini-chip.matched
- берёт: --accent, --accent-chip-bg, --accent-hover-soft, --accent-option-active, --accent-row-hover, --bg-primary, --bg-secondary, --bg-tertiary, --border, --err, --score-warn, --scrim, --text-primary, --text-secondary, --text-tertiary

### styles/vacancy-card.css (173)
- Карточка вакансии: шапка со статусом, чипы разбора, стек, текст и связи. Лента переходов — в timeline.css, выбор статуса — в status-picker.css, исходный текст — в raw-text.css, кружок с именами — в contact-block.css.
- селекторы (22): .det-head, .status-wrap, .det-title, .det-section, .status-badge, .status-badge:hover, .status-label, .status-badge .material-symbols-outlined, .status-wrap.popover-open .status-badge .material-symbols-outlined, .det-info, .info-chip, .info-chip .material-symbols-outlined, .info-chip.linkable, .info-chip.linkable:hover, .info-chip.score, .info-chip.score[data-tone='warn'], .info-chip.score[data-tone='bad'], .det-stack, .stack-chip, .stack-chip.matched, .det-section p, .vac-contacts
- берёт: --accent, --accent-chip-bg, --bg-primary, --bg-secondary, --bg-tertiary, --border, --err, --score-warn, --text-primary, --text-secondary

### styles/vacancy-filters.css (146)
- Панель отбора вакансий: что стоит внутри окошка поверх списка. Оправа окошка — общая, в popover.css; группы условий — в filter-group.css.
- селекторы (20): .filter-btn.active, .filter-panel, .filter-head, .filter-head .material-symbols-outlined, .filter-title, .filter-meta, .filter-close, .filter-close:hover, .filter-close .material-symbols-outlined, .filter-body, .filter-panel .input, .filter-body .status-dot, .filter-body .choice:hover, .filter-pair, .filter-dates, .filter-dates .date-picker:last-child .date-panel, .filter-foot, .filter-foot .btn, .filter-foot .btn .material-symbols-outlined, .filter-foot-right
- берёт: --accent, --bg-tertiary, --border, --scrim, --selected-bg, --surface-hover-firm, --text-primary, --text-secondary, --text-tertiary

### styles/wizard.css (490)
- Мастер первого запуска: окно из трёх полос — шаги, тело, подвал. Полосы те же, что у самого приложения, и это нарочно: мастер — не отдельная программа, а первый разговор с этой.
- селекторы (73): .wiz-window, .wiz-steps, .wiz-steps.dimmed, .wiz-step, .wiz-step::before, .wiz-step:first-child::before, .wiz-step[data-mark='active']::before,
.wiz-step[data-mark='done']::before, .wiz-step-mark, .wiz-step[data-mark='active'] .wiz-step-mark, .wiz-step[data-mark='done'] .wiz-step-mark, .wiz-step-label, .wiz-step[data-mark='active'] .wiz-step-label, .wiz-step[data-mark='done'] .wiz-step-label, .wiz-body, .wiz-body > *:last-child, .wiz-head, .wiz-head .material-symbols-outlined, .wiz-head h1, .wiz-title, .wiz-text, .wiz-text strong, .wiz-foot, .wiz-foot-right, .wiz-trouble, .wiz-done, .wiz-done .material-symbols-outlined, .wiz-done h2, .wiz-done .wiz-text, .wiz-subtitle, .wiz-subtitle strong, .wiz-welcome, .warning-card,
.info-card, .warning-card, .warning-card .material-symbols-outlined, .warning-card strong, .info-card, .info-card .material-symbols-outlined, .info-card strong, .wiz-body > .info-card,
.wiz-body > .warning-card, .help, .help strong, .help code, .help ol, .help ol li, .status-row, .status-row .material-symbols-outlined, .status-row[data-tone='ok'], .status-row[data-tone='ok'] .material-symbols-outlined, .status-row[data-tone='err'], .status-row[data-tone='err'] .material-symbols-outlined, .status-row[data-tone='busy'] .material-symbols-outlined, @keyframes wiz-spin, .radio-card, .radio-card:hover, .radio-card.selected, .radio-card.disabled, .radio-card.disabled:hover, .radio-card input, .radio-card.disabled input, .radio-card .rc-title, .radio-card .rc-sub, .file-pick, .file-pick.has-file, .file-pick .material-symbols-outlined, .file-pick .text, .file-pick .text .name, .wiz-window .input, .wiz-window .btn, .wiz-window .btn .material-symbols-outlined, .wiz-fields, .wiz-modes, .wiz-window .cdd-btn, .wiz-fields .help
- берёт: --accent, --accent-chip-selected, --accent-hover-soft, --alert-card-bg, --alert-card-border, --alert-text, --bg-primary, --bg-secondary, --bg-tertiary, --border, --err, --info, --info-card-bg, --info-card-border, --ok, --text-primary, --text-secondary, --text-tertiary

## tests — 29 файлов

### tests/attempts.test.js (42)
- —

### tests/autosave.test.js (94)
- —

### tests/blacklist_menu_item.test.js (80)
- * Файлы разметки вместе с содержимым.

### tests/bridge.test.js (113)
- —

### tests/calendar.test.js (50)
- —

### tests/card_links.test.js (37)
- —

### tests/chat.test.js (157)
- —

### tests/companies.test.js (91)
- —

### tests/contacts.test.js (471)
- —

### tests/dates.test.js (93)
- —

### tests/events.test.js (176)
- * Мост, отвечающий заготовленным, а на исходе — закрытой очередью.

### tests/experience.test.js (60)
- —

### tests/flash.test.js (34)
- —

### tests/footer.test.js (149)
- —

### tests/keys.test.js (97)
- —

### tests/logs.test.js (143)
- —

### tests/notes_field.test.js (64)
- * Файлы разметки, ставящие поле заметки, вместе с их содержимым.

### tests/outside.test.js (90)
- * Узел, считающий своими только перечисленные цели.

### tests/paged_list.test.js (108)
- * Подставной мост, отвечающий заготовленным и помнящий, о чём спрашивали.

### tests/paging.test.js (55)
- —

### tests/profile.test.js (96)
- —

### tests/settings.test.js (242)
- —

### tests/skills.test.js (92)
- —

### tests/stats.test.js (228)
- —

### tests/vacancies.test.js (202)
- —

### tests/vacancy_actions.test.js (117)
- —

### tests/vacancy_card.test.js (278)
- —

### tests/vacancy_filter.test.js (241)
- —

### tests/wizard.test.js (163)
- —

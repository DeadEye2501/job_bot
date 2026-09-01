# Карта фронта

Собрана из кода. Число в скобках — строк в файле.

## api — 2 файлов

### api/bridge.js (86)
- * Отказ моста — один на все его роды. * * Род один нарочно: экран показывает отказы единой плашкой и по роду не * ветвится. Различает их фраза — и ничего, кроме неё, отсюда не читают: род и * поля из конверта тут лежали, но не спрашивал их ни один экран.
- отдаёт: Refused, call, ready

### api/events.js (111)
- * Слушатель вестей поверх зова, который спрашивает мост «что нового после N». * * Зов приходит доводом, а не берётся отсюда: так цикл проверяется без окна и * без моста вовсе, а другого способа его проверить нет — он бесконечен по * устройству.
- отдаёт: listener

## app — 26 файлов

### app/BlacklistList.svelte (218)
- —
- принимает: ask, say, events

### app/BottomBar.svelte (242)
- Тумблер режима не запирается ничем: режим — выбор человека, и погасшая лампочка не повод не дать его сменить. Двум лампочкам из четырёх переписка вовсе не нужна, а запертый тумблер при мёртвом Telegram оставлял бы человека с ботом, которого нечем выключить.
- принимает: ask, say, events, onlocked, oncontact

### app/ChannelCard.svelte (278)
- Легенда под полосой: одиннадцать цветов без подписей не читаются, а подписать отрезки внутри полосы негде.
- принимает: ask, say, lockedTip, events, channelId, onvacancy, onclose, onchanged

### app/ChannelsList.svelte (203)
- Один переключатель на весь список: он же и показывает, все ли каналы опрашиваются.
- принимает: ask, say, lockedTip, events, open, onopened, onvacancy
- берёт: ./ChannelCard.svelte

### app/CompaniesList.svelte (107)
- —
- принимает: ask, say, events, open, onopened, onperson, onvacancy
- берёт: ./CompanyCard.svelte

### app/CompanyCard.svelte (254)
- Написания: под ними компания приходит в объявлениях. Потеряй карточка одно из них — следующая вакансия завела бы компанию заново.
- принимает: ask, say, companyId, onperson, onvacancy, onclose, onchanged

### app/ContactsScreen.svelte (79)
- —
- принимает: ask, say, lockedTip, events, openCard, onopened, onvacancy
- берёт: ./BlacklistList.svelte, ./ChannelsList.svelte, ./CompaniesList.svelte, ./PeopleList.svelte

### app/LogsScreen.svelte (197)
- —
- принимает: ask, events, say

### app/PeopleList.svelte (103)
- —
- принимает: ask, say, events, open, onopened, oncompany, onvacancy
- берёт: ./PersonCard.svelte

### app/PersonCard.svelte (257)
- Своя запись на каждого человека: поле запечатывает номер при заведении, и заводиться заново на каждого его заставляет именно `{#key}` — без него запечатанный номер протухнет.
- принимает: ask, say, events, personId, oncompany, onvacancy, onclose, onchanged
- берёт: ./PersonChat.svelte

### app/PersonChat.svelte (279)
- Строка отправки остаётся на месте и при заслоне, только запертой: пропав, она не сказала бы, почему писать нельзя.
- принимает: ask, say, hrId, blocked, events, onread

### app/ProfileCv.svelte (220)
- —
- принимает: ask

### app/ProfileExperience.svelte (146)
- —
- принимает: ask

### app/ProfileScreen.svelte (30)
- —
- принимает: ask
- берёт: ./ProfileCv.svelte, ./ProfileExperience.svelte, ./ProfileSkills.svelte

### app/ProfileSkills.svelte (176)
- —
- принимает: ask

### app/SettingsScreen.svelte (346)
- Окно входа стоит внутри поля настроек, а не рядом с ним: кнопки в нём той же плотности, что и остальные кнопки экрана, и берут они её отсюда. На раскладку это не влияет — окно висит поверх страницы.
- принимает: ask, say
- берёт: ./TelegramLogin.svelte

### app/Shell.svelte (251)
- —
- берёт: ./BottomBar.svelte, ./ContactsScreen.svelte, ./LogsScreen.svelte, ./ProfileScreen.svelte, ./SettingsScreen.svelte, ./StatsScreen.svelte, ./VacanciesScreen.svelte, ./WizardScreen.svelte

### app/StatsScreen.svelte (124)
- Числа считает бот, а не окно: пересчитать за тот же срок иначе нечем — пришлось бы уходить в другой раздел и возвращаться.
- принимает: ask, onslice, onchannel

### app/TelegramLogin.svelte (96)
- Окно пересоздаётся на смене шага: код и облачный пароль — разные секреты, и набранный код не должен доехать до поля пароля.
- принимает: say, creds, relogin, ondone, onclose

### app/VacanciesScreen.svelte (431)
- —
- принимает: ask, say, lockedTip, events, oncontacts, open, onopened, openFilter, onfiltered
- берёт: ./VacancyCard.svelte

### app/VacancyCard.svelte (399)
- Совпавшее с анкетой подсвечено: по нему видно, чем вакансия набрала свою оценку.
- принимает: ask, say, events, lockedTip, vacancyId, oncontacts, onclose, onchanged
- берёт: ./VacancyLinks.svelte

### app/VacancyLinks.svelte (126)
- —
- принимает: ask, say, vacancyId, kind, prefill, current, onclose, onlinked

### app/WizardCv.svelte (191)
- —
- принимает: ask, busy, events, onback, onnext

### app/WizardLlm.svelte (305)
- —
- принимает: ask, kind, onback, onnext

### app/WizardScreen.svelte (162)
- Приглушена только обложка: на финале четыре галочки горят в полную силу — это и есть то, ради чего мастер проходили.
- принимает: ask, say, events, ondone, completed
- берёт: ./WizardCv.svelte, ./WizardLlm.svelte, ./WizardTelegram.svelte

### app/WizardTelegram.svelte (112)
- —
- принимает: ask, say, onback, onnext
- берёт: ./TelegramLogin.svelte

## components — 89 файлов

### components/ActionsMenu.svelte (30)
- —
- принимает: children

### components/AddBlacklistDialog.svelte (113)
- Поле одно на оба рода: у слова подсказчика нет вовсе, и второе написание того же поля разошлось бы с первым первой же правкой длины. Обёртка стоит всегда — она держит выпадающий список у поля.
- принимает: draft, hints, kinds, saving, onkind, onvalue, onreason, onadd, onclose
- берёт: ./ModalFoot.svelte, ./ModalHead.svelte, ./ModalShell.svelte

### components/AddChannelDialog.svelte (48)
- Курсор ставится в поле сразу: окно об одном поле и открывают затем, чтобы в него набрать. Проверка a11y гасится нарочно — она о формах, где полей несколько и выбор первого за человеком.
- принимает: value, trouble, saving, oninput, onadd, onclose
- берёт: ./ModalFoot.svelte, ./ModalHead.svelte, ./ModalShell.svelte

### components/AskDialog.svelte (67)
- Окно берёт на себя Escape, но не Enter: в нём набирают заметки в несколько строк, и подтверждение по Enter обрывало бы заведение на первом же переводе строки.
- принимает: icon, extra, title, confirmLabel, busyLabel, busy, ready, onconfirm, oncancel, children
- берёт: ./ModalFoot.svelte, ./ModalHead.svelte, ./ModalShell.svelte

### components/Avatar.svelte (20)
- —
- принимает: avatar, name, icon

### components/BlacklistChip.svelte (15)
- —
- принимает: value

### components/BlacklistMark.svelte (13)
- —
- принимает: blocked

### components/BlacklistMenuItem.svelte (21)
- —
- принимает: blocked, close, onblock, onunblock
- берёт: ./MenuItem.svelte

### components/BlacklistRow.svelte (120)
- —
- принимает: row, onedit, ontoggle, onremove
- берёт: ./RowToggle.svelte

### components/BulletList.svelte (36)
- —
- принимает: label, addLabel, items, onedit, onadd, onremove

### components/CardHandle.svelte (23)
- —
- принимает: username, onopen

### components/CardPane.svelte (20)
- —
- принимает: trouble, ready, children

### components/ChannelRow.svelte (60)
- Нажимается вся строка, а не имя в ней: нажатие на одном имени оставляет мёртвыми отступы строки, кружок и хвост. Кнопкой строка быть не может — в ней стоит переключатель опроса, — поэтому клавиатуре она отвечает разметкой. Клавишу строка принимает только свою: у переключателя внутри неё нажатие клавиши всплывает сюда, и без этого Enter на переключателе открывал бы карточку вместо переключения.
- принимает: channel, selected, onpick, ontoggle
- берёт: ./Avatar.svelte, ./BlacklistMark.svelte, ./Handle.svelte, ./RowToggle.svelte

### components/ChatBubble.svelte (62)
- Вложение открывает система, а не страница: показать документ она умеет только снимком, а читают его в своей программе. Файла может и не быть вовсе: бот скачивает не всё, — и тогда остаётся род вложения в скобках, потому что открывать нечего.
- принимает: message, onopen

### components/Chip.svelte (14)
- —
- принимает: text, onremove

### components/ChipList.svelte (58)
- Курсор ставится в поле сразу: его и завели по нажатию «добавить». Проверка a11y гасится нарочно — она о формах, где полей несколько и выбор первого за человеком.
- принимает: items, onadd, onremove
- берёт: ./Chip.svelte

### components/ChoiceRow.svelte (27)
- —
- принимает: options, chosen, look, dots, onpick

### components/CompanyRow.svelte (41)
- —
- принимает: company, selected, onpick
- берёт: ./Avatar.svelte, ./BlacklistMark.svelte

### components/ConfirmDialog.svelte (21)
- —
- принимает: message, confirmLabel, tone, onconfirm, oncancel
- берёт: ./ModalShell.svelte

### components/ContactActions.svelte (23)
- —
- принимает: mergeLabel, blocked, onmerge, onblock, onunblock, ondelete
- берёт: ./ActionsMenu.svelte, ./BlacklistMenuItem.svelte, ./MenuItem.svelte

### components/ContactsPanes.svelte (58)
- —
- принимает: loaded, empty, chosen, detailEmpty, onlistscroll, ondetailscroll, toolbar, emptyNote, items, detail

### components/CvFileRow.svelte (24)
- Открывать нечего, когда файла нет на диске: система показала бы свою ошибку вместо нашей строки «файл не найден».
- принимает: meta, onreplace, onopen

### components/DatePicker.svelte (149)
- —
- принимает: value, onpick, disabled, up

### components/DelayedTextarea.svelte (28)
- —
- принимает: value, maxlength, placeholder, ontyped, onflush

### components/DonutChart.svelte (42)
- —
- принимает: parts, total, label

### components/DraftChips.svelte (23)
- —
- принимает: draft, field, caption
- берёт: ./ChipList.svelte

### components/DraftNotes.svelte (21)
- —
- принимает: draft

### components/DropPanel.svelte (28)
- Ключ по месту, а не по значению: имя человека уникальным не бывает, и у одного собеседника их трое с одним и тем же. Ключ по значению роняет отрисовку на первом же тёзке — панель не появляется вовсе и молча.
- принимает: options, value, onpick, keepFocus

### components/Dropdown.svelte (39)
- —
- принимает: options, value, onpick
- берёт: ./DropPanel.svelte

### components/ExperienceCard.svelte (148)
- Нажимается вся шапка, а не одна стрелка: свёрнутых карточек столбик, и целиться в значок ради раскрытия человеку не за что.
- принимает: exp, known, open, ontoggle, onedit, onremove
- берёт: ./BulletList.svelte, ./DatePicker.svelte, ./SkillPicker.svelte

### components/FilterGroup.svelte (12)
- —
- принимает: label, children

### components/Handle.svelte (17)
- —
- принимает: username

### components/HealthLamp.svelte (9)
- —
- принимает: name, state, title

### components/LangRows.svelte (49)
- —
- принимает: rows, onedit, onadd, onremove
- берёт: ./Dropdown.svelte

### components/LlmSection.svelte (116)
- Ввод в любое из полей гасит плашку проверки: она говорит «модель отвечает» про тот адрес, который проверяли, и на изменённых полях лгала бы. Ловится здесь, а не на каждом поле: событие всплывает, и второй обработчик у поля секрета пришлось бы заводить внутри чужого компонента.
- принимает: title, icon, creds, models, pill, busy, sameAsChat, onsave, onprobe, onsame, onedit
- берёт: ./SecretInput.svelte, ./SettingsSection.svelte, ./SuggestInput.svelte

### components/LogLevelPill.svelte (17)
- —
- принимает: label, icon, tone, count, active, onpick

### components/LogRow.svelte (27)
- Нажимается вся строка, а не значок в ней: строк сотни, и целиться в значок ради трассировки человеку не за что. Клавиатуре она отвечает тем же — иначе журнал не развернуть, не берясь за мышь.
- принимает: time, level, tone, source, message, details, expanded, ontoggle

### components/MenuItem.svelte (38)
- —
- принимает: icon, label, danger, title, blocked, disabled, close, onpick

### components/MergeDialog.svelte (32)
- —
- принимает: title, placeholder, empty, load, asRow, onapply, onclose
- берёт: ./PickerDialog.svelte, ./PickerRow.svelte

### components/MiniPeople.svelte (40)
- —
- принимает: people, empty, onpick
- берёт: ./Avatar.svelte

### components/MiniVacancies.svelte (42)
- —
- принимает: vacancies, empty, loading, onpick

### components/ModalFoot.svelte (15)
- —
- принимает: label, busyLabel, busy, ready, oncancel, onconfirm

### components/ModalHead.svelte (23)
- —
- принимает: icon, title, meta, onclose

### components/ModalKeys.svelte (17)
- —
- принимает: close, confirm

### components/ModalShell.svelte (34)
- Нажатие по затемнению закрывает окно, нажатие внутри коробки — нет: сверяем, что нажали ровно в затемнение, а не всплыло из содержимого.
- принимает: extra, over, confirm, awayCloses, onclose, children
- берёт: ./ModalKeys.svelte

### components/ModeToggle.svelte (24)
- —
- принимает: mode, onpick

### components/NavGroup.svelte (9)
- —
- принимает: icon, label, active, onpick

### components/NewCardDialog.svelte (75)
- Ряд способов только у вакансии: её заводят двумя — набирают поля сами или отдают боту текст объявления. У человека и компании второго нет вовсе. Ряд тот же, что у грейда и формата: свой разошёлся бы с ними видом.
- принимает: kind, draft, busy, ready, options, oncompany, onhr, onconfirm, oncancel
- берёт: ./AskDialog.svelte, ./ChoiceRow.svelte, ./NewCompanyFields.svelte, ./NewPersonFields.svelte, ./NewVacancyFields.svelte, ./PastedVacancyFields.svelte

### components/NewCompanyFields.svelte (35)
- Написания набирают по одному, как в карточке компании: их сверяют поштучно, и набранные одной строкой они читались бы как одно длинное написание, под которым компания не приходит никогда.
- принимает: draft
- берёт: ./DraftChips.svelte, ./DraftNotes.svelte

### components/NewPersonFields.svelte (34)
- Номер учётной записи — только цифры: на телефоне открывается цифровая раскладка, а мост всё равно приводит его к числу.
- принимает: draft
- берёт: ./DraftNotes.svelte

### components/NewVacancyFields.svelte (110)
- Дата сразу под названием: она про само объявление, а не про то, чего от кандидата ждут, и место ей рядом с тем, чем объявление называется.
- принимает: draft, options, oncompany, onhr
- берёт: ./ChoiceRow.svelte, ./DraftChips.svelte, ./DraftNotes.svelte, ./PostedAtField.svelte, ./SuggestInput.svelte

### components/NotesField.svelte (74)
- —
- принимает: value, placeholder, owner, save

### components/PastedVacancyFields.svelte (24)
- —
- принимает: draft
- берёт: ./PostedAtField.svelte

### components/PersonRow.svelte (47)
- Ник и компания красятся порознь: по нику находят в Telegram, по компании вспоминают, откуда человек писал.
- принимает: person, selected, onpick
- берёт: ./Avatar.svelte, ./BlacklistMark.svelte, ./Handle.svelte

### components/PickList.svelte (54)
- —
- принимает: placeholder, hint, empty, names, chosen, search, onsearch, prefix, onpick

### components/PickerDialog.svelte (149)
- Пустых слов два, и разница несущая: «ничего не найдено» говорит, что список есть, а показать из него нечего, — и человек ищет причину в поле поиска, а не в том, что заводить он ещё ничего не начинал.
- принимает: title, icon, placeholder, empty, prefill, current, preselect, load, applyLabel, onapply, saving, onclose, children, createLabel, createIcon, oncreate
- берёт: ./ModalFoot.svelte, ./ModalHead.svelte, ./ModalShell.svelte, ./SearchBox.svelte

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

### components/PostedAtField.svelte (24)
- —
- принимает: draft, up
- берёт: ./DatePicker.svelte

### components/ProgressBars.svelte (25)
- —
- принимает: channels, messages, text

### components/RawTextDialog.svelte (36)
- Кнопка стоит поверх текста и полупрозрачна: окно узкое, и вынесенная в подвал она отняла бы у текста строку ради того, что нажимают раз в десять открытий.
- принимает: id, chips, text, oncopy, onclose
- берёт: ./ModalHead.svelte, ./ModalShell.svelte

### components/RowToggle.svelte (40)
- Нажатие дальше не идёт: строка вокруг переключателя бывает нажимаемой сама, и тогда переключение открывало бы её заодно с собой.
- принимает: checked, disabled, title, ontoggle

### components/RunButton.svelte (13)
- —
- принимает: running, disabled, title, onpress

### components/SearchBox.svelte (36)
- —
- принимает: value, placeholder, maxlength, onsearch

### components/SecretInput.svelte (32)
- —
- принимает: value, placeholder, mono, maxlength, onsave

### components/SettingsSection.svelte (17)
- —
- принимает: icon, title, pill, danger, children
- берёт: ./StatusPill.svelte

### components/SkillPicker.svelte (82)
- —
- принимает: chosen, known, onadd, onremove
- берёт: ./Chip.svelte, ./SearchBox.svelte

### components/SkillRow.svelte (51)
- —
- принимает: skill, onedit, onremove
- берёт: ./ChipList.svelte

### components/StatsCard.svelte (15)
- —
- принимает: title, ready, span, children

### components/StatsChannelsCard.svelte (121)
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

### components/StatsStatusCard.svelte (40)
- —
- принимает: counts, onpick
- берёт: ./DonutChart.svelte

### components/StatusPicker.svelte (77)
- Заперты на время записи обе кнопки внизу: пока ответ в пути, отмена оставила бы человека думать, что перехода не было, — а он уже уехал. Escape при этом ловится на всё окно, а не в одном поле: окошко открывают нажатием по пилюле, и фокус в этот миг стоит на ней, а не в причине.
- принимает: status, saving, wrap, onapply, oncancel
- берёт: ./ModalKeys.svelte

### components/StatusPill.svelte (6)
- —
- принимает: text, tone, title

### components/SuggestInput.svelte (103)
- —
- принимает: value, options, placeholder, asked, mono, maxlength, onsave
- берёт: ./DropPanel.svelte

### components/TelegramSection.svelte (51)
- —
- принимает: tg, draft, busy, onedit, onlogin, onlogout
- берёт: ./SecretInput.svelte, ./SettingsSection.svelte

### components/TgLoginDialog.svelte (61)
- Escape закрывает, Enter — нет: шаг уходит только кнопкой.
- принимает: step, phone, relogin, busy, error, onsubmit, oncancel
- берёт: ./ModalShell.svelte

### components/TopTabs.svelte (12)
- —
- принимает: tabs, active, onpick

### components/UnreadBadge.svelte (49)
- Затемнения нет вовсе, но нажатие мимо список закрывает: он висит поверх окна, и оставленный открытым перекрывал бы правый край полосы.
- принимает: count, open, loading, rows, ontoggle, onpick

### components/VacancyActions.svelte (67)
- —
- принимает: blocks, say, onsend, onrerun, onlinkhr, onlinkcompany, onraw, onsource, ondelete
- берёт: ./ActionsMenu.svelte, ./MenuItem.svelte

### components/VacancyFilters.svelte (263)
- Панель падает из полосы, а не из-под кнопки: она вдвое шире полосы, и прижатая к кнопке у правого края она уходила бы за кромку списка. Обёртка вокруг них своей раскладки не имеет и стоит только затем, чтобы кнопка и панель считались одним местом: «мимо» сторож считает по узлу, а не по имени класса, и кнопка панели не принадлежит — она её сосед.
- принимает: applied, options, onapply, shown, onshown
- берёт: ./ChoiceRow.svelte, ./DatePicker.svelte, ./FilterGroup.svelte, ./PickList.svelte

### components/VacancyRow.svelte (38)
- Половины подписи покрашены по-разному: компанию читают первой, а давность — последней, и одинаковый цвет заставлял бы разбирать строку целиком.
- принимает: vacancy, threshold, selected, onpick

### components/VacancyTimeline.svelte (107)
- —
- принимает: rows, vacancyId, onsave

### components/WizardFoot.svelte (34)
- Заперта вместе с основной: уход назад посреди зова оставил бы ответ прилетать в экран, которого уже нет.
- принимает: nextLabel, nextIcon, busy, onback, onnext, children

### components/WizardStatus.svelte (20)
- —
- принимает: status

### components/WizardSteps.svelte (16)
- —
- принимает: marks, dimmed

## state — 55 файлов

### state/alive.js (59)
- * Заводит признак жизни экрана.
- отдаёт: living

### state/attempts.js (34)
- * Завести свой счёт попыток. * * Заводится он на каждое место, где запросы обгоняют друг друга, — поиск, * прокрутка, переключение вкладок. Общий счётчик на страницу отбрасывал бы * ответы соседнего экрана. * * Начатую работу счёт не останавливает — остановить её со страницы нечем, — а * обесценивает её ответ: пришедший последним не считается свежим, если после * него успели спросить заново. * * **Это не про закрытие окна.** Свежим тут считается ровно один запрос, а окно * спрашивает мост вперемешку — здоровье, непрочитанное, режим, — и соседний * ответ такой счёт объявил бы устаревшим. Уход со страницы оболочка сторожит * своим признаком: там гасится всё разом, а не последнее.
- отдаёт: attempts

### state/autosave.js (70)
- * Заводит отложенную запись поля. * * Пауза считается от последнего знака: запись на каждый знак послала бы мосту * по вопросу на букву, а отсчёт от первого отправлял бы недописанное. * * `save` отвечает, легло ли: ложь означает отказ, и тогда набранное считается * незаписанным — следующая попытка уедет тем же текстом.
- отдаёт: autosave

### state/autosize.js (51)
- * Подогнать высоту поля под его текст. * * Сжатие до `auto` перед замером несущее: растянутое поле показывает прежнюю * высоту и после того, как текст из него убрали, — стёртый абзац оставил бы * после себя дыру во весь свой рост.
- отдаёт: fitHeight, growing

### state/avatar.js (19)
- * Буквы имени на месте снимка. * * Снимок есть не у всех: у заведённых руками его нет вовсе, а пустой кружок * читается как недогрузившаяся картинка. Берутся первое слово и последнее — * имя и фамилия; отчество между ними ничего не различает.
- отдаёт: initials

### state/blacklist.js (137)
- * Роды строк отсева. Первый — общий: в нём экран открывается. * * Порядок несущий: слова стоят перед предметами, потому что ими отсев и * пользуются чаще всего — по одному слову отсеивается больше объявлений, чем по * всем каналам вместе.
- отдаёт: BLACKLIST_KINDS, blacklistCounts, blacklistHints, blacklistShown, blankRow, blockNote, unblockNote, valueField

### state/calendar.js (69)
- * Дни недели с понедельника. Порядок несущий: по нему считается, в какую * колонку встаёт первое число месяца.
- отдаёт: WEEKDAYS, monthGrid, monthTitle, shiftMonth

### state/card_actions.svelte.js (54)
- * Заводит действия карточки над собой. * * `id` спрашивают, а не передают значением: панель одна на всю вкладку, и * карточку в ней переключают нажатием по соседней строке.
- отдаёт: cardActions

### state/card_block.js (36)
- * Заводит перемену отсева. * * Имена методов приходят литералами: собранное из частей имя не найдётся * поиском по шву, и переименование на мосту нашлось бы только с экрана. * * `female` — про кого речь: «занесён» про компанию человек читает как опечатку. * Слова при этом общие на все три карточки (`state/blacklist.js`) — написанные * порознь, они разошлись бы и остальным. * * Карточку и список перечитывают оба: отметка отсева стоит и в самой карточке, * и в её строке списка, и необновлённая заставила бы нажать второй раз. * * Отказ молчит и не перечитывает ничего: плашку человек уже увидел, а * перечитанная карточка показала бы ровно то же.
- отдаёт: cardBlocking

### state/card_finish.js (32)
- * Заводит действие, кончающее карточку. * * `note` — чем сказано о случившемся: «Канал удалён» и «Карточки слиты» человек * читает как вести о разном, и общее слово посылало бы его гадать. * * Список зовут прежде закрытия: закройся панель раньше, снесённая строка * осталась бы под ней до следующего чтения списка. * * Отказ не закрывает панель и молчит: плашку об отказе человек уже увидел, а * закрытая панель поверх неё читается как «сделано». * * Отвечает, случилось ли: слияние по этому ответу гасит своё окно выбора, а по * отказу оставляет его открытым — выбранное в нём ещё нужно.
- отдаёт: cardFinish

### state/card_links.js (25)
- * Три связи карточки: две внутрь и одна в подборщик. * * Пустая связь названа пустотой, а не пропущена: карточка ставит на её место * неподвижную подпись, и разбирать, чего в ответе нет, ей было бы нечем. * * Имя компании без привязки ведёт не в контакты, а в подборщик с этим самым * именем: связи нет, но разбор её узнал — человек нажимает и сразу видит * совпадения, вместо того чтобы набирать то же слово руками.
- отдаёт: cardLinks

### state/card_notes.js (27)
- * Заводит запись заметки. * * Карточку не перечитываем: человек мог набрать ещё, пока летел вопрос, и * пришедшее из базы стёрло бы это. Записанным считаем набранное — этот зов * называет только поправленные поля, самой заметки в ответе нет, — а пустая от * пробельной здесь не отличается, обе сводятся к пустоте по дороге. * * Ответ в закрытую карточку не кладётся: панель закрывают, не дожидаясь записи, * и сказанное ей всплыло бы над следующей, открытой на её месте. * * `null` значит «не легло»: поле по нему считает набранное несохранённым, и * следующая попытка уедет тем же текстом.
- отдаёт: cardNotes

### state/card_read.js (49)
- * Заводит чтение карточки. * * `trouble` — чем назвать неудачу: «карточку», «компанию» и «канал» человек * читает по-разному, и общее слово посылало бы его не туда. * * `alive` спрашивают, а не передают значением: панель закрывают, пока ответ в * пути, и класть его тогда уже некуда. * * `ask` принимается обёрткой, а не самим доводом: довод читается один раз, при * заведении, и подмена его сверху сюда бы не доехала. * * Показанное отдаётся парой — карточка и слово о беде разом: положи их * карточка порознь, третье состояние («ответ негоден, не трогать ничего») * пришлось бы разбирать в каждой из трёх, и одна опять разобрала бы иначе. * * `show` кладёт эту пару в состояние карточки. Через довод, а не ответом: * ответ разбирали три карточки, и разбор был у них дословно один — проверка * на негодность и распаковка пары. Своими у них остаются только имена полей, * а имя подставить за карточку нельзя.
- отдаёт: cardRead

### state/card_save.js (22)
- * Заводит запись правки поля. * * Перечитываем и после отказа: поля правятся на месте, и отклонённое мостом * значение — а негодный ник мост отклоняет — осталось бы на экране. Человек * читал бы своё, а в базе лежало бы прежнее. * * Списку говорят только по удаче: не изменилось ничего, и перечитывать его * значило бы гонять мост ради того же вида.
- отдаёт: cardSave

### state/channels.js (105)
- * Чем подписать канал в списке. * * Название — сверху, ник — под ним: по названию канал узнают, по нику ищут. * Названия у канала может не быть — тогда его место занимает ник, а совсем * безымянный назван номером: показать нечего, но строка должна остаться * нажимаемой.
- отдаёт: channelName, channelStats, channelTitle, channelToggle, channelsToggle, pollBlock

### state/chat.js (115)
- * Разложить письма по дням, сохранив их порядок. * * Подпись дня стоит над первым письмом этого дня, а не над каждым: иначе лента * превращается в чересполосицу дат. * * Письмо без времени выпадает вовсе — поставить его некуда, а под чужой * подписью дня оно соврало бы.
- отдаёт: attachmentKind, byDays, chatTime, isUnread, sendBlock, tick, unread

### state/chosen.js (50)
- * Какую долю дорожки залить под это значение. * * Зажато с обеих сторон: значение приезжает с моста и могло быть выставлено * до того, как предел назначили, — заливка шире дорожки выглядит поломкой, а * отрицательная не рисуется вовсе.
- отдаёт: alone, fillPercent, toggled, without

### state/companies.js (103)
- /i; /** Чем подписать компанию в списке. * * Имя — сверху, сайт и алиасы — под ним: по имени компанию узнают, по * домену различают. Две «Ромашки» с разными сайтами — разные компании, и без * второй строки они неотличимы. * * Имени может не быть — оно приходит из объявления, — и тогда компания названа * номером: показать нечего, но строка должна остаться нажимаемой.
- отдаёт: blankCompany, companyCandidate, companyLine, companyNamed, companyTitle, siteHref

### state/contact_adding.svelte.js (85)
- * Заводит окно заведения карточки. * * `list` — уже заведённый список этой вкладки: перечитывают его и отсюда, * заведя карточку, и сама вкладка по вести о правке. * * `save` отправляет черновик и отвечает пустотой на отказ — тем же словом, * каким отвечает мост.
- отдаёт: contactAdding

### state/contacts_watch.js (24)
- * Заходит на вкладку и отдаёт снятие — его и возвращают из эффекта. * * Перечитывает по вести не страницей, а показанным: иначе занесение в отсев из * карточки схлопывало бы пролистанное до первой страницы.
- отдаёт: watchContacts

### state/dates.js (111)
- * Дата для тесной колонки: день, сокращённый месяц и год чужого года. * * Год этого года не пишется: он и так известен, а колонка узка. Негодное и * пустое дают пустоту — прочерк в такой колонке читался бы как значение.
- отдаёт: asIso, dayOf, isoDay, padded, shortDate, showDate, showStamp, validDate

### state/experience.js (83)
- * Период работы для шапки карточки. * * Месяц и год без дня: места работы различают по месяцам, а день удлиняет * строку вдвое. Открытый конец назван словами — по нему и читают, работает * человек здесь сейчас или нет.
- отдаёт: cardTitle, experienceGoing, experienceReady, period

### state/flash.js (24)
- * Заводит отметку, которая гаснет сама. * * Второе зажигание подряд отсчёт продлевает, а не гасит: быстрая правка двух * полей иначе тушила бы рамку по времени первого, и вторая запись выглядела бы * незаписанной.
- отдаёт: flashing

### state/fresh.js (52)
- * Заводит зов, отбивающий устаревший ответ. * * Заводится на каждое место, где вопросы обгоняют друг друга: свой у поиска, * свой у прокрутки, свой у каждой панели. Общий на экран объявлял бы * устаревшим ответ соседнего вопроса — их спрашивают вперемешку. * * `alive` спрашивают, а не передают значением: экран закрывают, пока ответ в * пути, и класть его тогда уже некуда. * * Сам зов принимается обёрткой, а не именем метода с нагрузкой: мост зовут с * разным числом доводов, и «ничего» отличается у него от «ничего не передали». * * `null` значит «не класть ничего»: отказ моста, ушедший экран и обогнанный * ответ на месте различать некому — все трое означают одно. Отказ поэтому и не * отбивается своей веткой: мост отвечает на него пустотой, и она уходит * зовущему сама, тем же словом, что и два остальных исхода.
- отдаёт: freshAnswer, stillNeeded

### state/health.js (50)
- * Живо ли всё, на чём держится работа бота. * * По этому ответу отпираются кнопки режима и запуска, поэтому незнание считается * «не живо»: до первого ответа моста мы не знаем ничего, а отпертая на миг * раньше правды кнопка запускает бота без модели.
- отдаёт: LAMPS, allAlive, blockedTip, downNames

### state/keys.js (70)
- * Чем нажатая клавиша отзовётся в окне: закрытием, подтверждением или ничем. * * Многострочное поле — исключение: в нём Enter переносит строку. Иначе заметку * в два абзаца не набрать, первый же перевод строки отправил бы окно.
- отдаёт: modalKey, modalPress, opened, pressKey, saveKey

### state/logs.js (110)
- * Уровни на пилюлях — от беды к мелочи. Порядок постоянный: по нему человек * метит в нужную пилюлю, не читая подписей. * * `id` — то, что приходит в записи с питона; `tone` — имя цвета; значок * лигатурой шрифта. `CRITICAL` своей пилюли не имеет: его накрывает `ERROR`.
- отдаёт: AT_FIRST, LEVELS, askDelay, emptyText, levelTone, logTime, mayHide, shown

### state/mini_read.js (33)
- * Заводит чтение по номеру записи. * * `payload` собирает нагрузку из номера записи: у компании это одно имя поля, * у человека другое, и подставить его за карточку нельзя. * * `show` кладёт пришедшее. Через довод, а не ответом: разбор ответа — проверку * на негодность и взятие поля — карточки вели одинаково, и своими у них * остаются только имена.
- отдаёт: miniRead

### state/modes.js (61)
- * Три положения слева направо. Порядок несущий: по нему считается, в какую * треть дорожки попало нажатие.
- отдаёт: OFF, modeChosen

### state/new_card.js (61)
- * Обвязка формы заведения по роду карточки. * * `named` держится рядом с `blank` нарочно: пустой черновик и заслон, который * решает, что он уже не пустой, — две половины одного правила, и разъехавшись, * они дали бы кнопку, открытую над формой, которую мост отобьёт.
- отдаёт: NEW_CARD

### state/one_write.js (49)
- * Заводит запись, у которой в полёте не бывает двух снимков. * * `write` отвечает, а не бросает: отказ моста — обычное дело для анкеты, и все * трое зовущих ловят его у себя, каждый своими словами человеку. * * Отдаёт обещание, которое кончается вместе с отправкой снимка: на нём держится * и уход с вкладки — набранное должно успеть уехать. * * Кончается оно исходом последней уехавшей записи, а не своей: сведённый снимок * включает в себя все, что были до него, и «легло ли» — это про него.
- отдаёт: oneWrite

### state/open_mark.js (20)
- * Принять отметку и погасить её. * * Отметку ставят соседние экраны: воронка каналов в статистике, карточка * вакансии, вкладка компании. Без отметки не трогают ничего — вкладку * открывают и просто так. * * Гасится она сразу, а не по закрытии карточки: непогашенная открыла бы её * заново, и человек, закрывший карточку, читал бы это как поломку.
- отдаёт: takeOpened

### state/outside.js (43)
- * Ставит сторожа «нажали мимо» и отдаёт его снятие. * * Отдаётся снятие затем, что зовут это из эффекта: он и вернёт его окну. * * Узла может ещё не быть — разметка привязывает его после первого показа, — и * до тех пор мимо не нажимают ни разу: окошка на экране нет.
- отдаёт: closeOnClickAway, whileOpen

### state/paged_list.svelte.js (122)
- * Заводит список, читающий себя страницами. * * `ask` — обращение к мосту, `method` — имя метода, `key` — под каким именем * строки лежат в ответе. Обращение принимается обёрткой, а не самим доводом: * довод читается один раз, при заведении списка, и подмена его сверху сюда бы * не доехала.
- отдаёт: pagedList

### state/paging.js (68)
- * Сколько строк в странице. Столько же по умолчанию отдаёт мост.
- отдаёт: PAGE, VACANCY_PAGE, appended, nearBottom, nearTop, refreshLimit

### state/people.js (140)
- * Как назвать человека в чужой карточке. * * Безымянный назван номером: строка должна читаться, а не пустовать.
- отдаёт: blankPerson, named, personCandidate, personHead, personLine, personName, personSub, personTitle, unreadLine

### state/picker.js (76)
- * Отперта ли кнопка «Связать». * * Промах мышью по строке списка не должен менять привязку: выбор строки только * помечает её, а связывает отдельная кнопка. Выбор уже привязанного кнопку не * отпирает — нажатие переписало бы связь тем же значением и записало в ленту * перемену, которой не было.
- отдаёт: candidate, labelOf, labels, linkReady, sameName

### state/profile.js (108)
- * Грейды, какими их выбирают в анкете. Значения едут на мост и совпадают с * перечнем `backend/domain/taxonomy.py`.
- отдаёт: GRADES, LANG_LEVELS, WORK_FORMATS, blankProfile, cvNote, fileSize, langRow, named, updatedNote

### state/progress.js (72)
- * Подпись начатого обхода, о котором ещё ничего не известно. * * Первая весть о ходе приходит не сразу: до неё полосы уже бегут, и подпись под * ними обязана сказать, чем именно бот занят.
- отдаёт: COUNTLESS_STAGES, STARTING, bar, caption, countlessNote

### state/provider.js (48)
- * Спросить у поставщика имена его моделей. * * Отказ и пустой перечень — разные ответы, и путать их нельзя: первое значит * «сервер не отозвался», второе — «сервер поднят, но модели в нём нет», и * чинятся они по-разному. Отказ приходит фразой, а не пустотой. * * Имя модели в вопрос не идёт: перечень читается с адреса и ключа, а имя — как * раз то, что в нём ищут.
- отдаёт: askModels, probeModel

### state/search.js (25)
- * Что из списка остаётся видно под набранное. * * Пустое набранное оставляет список целым: поле поиска стоит над уже открытым * списком, и до первого знака резать нечего. Одни пробелы — то же самое: их * набирают между словами и стирают последними, и схлопнутый на них список * мигал бы под руками. * * Регистр не различается — человек набирает как придётся, а значения приходят * как записаны. Вхождением, а не началом строки: имена приходят с приставками * («qwen/qwen3-4b», «@ник · компания»), и отбор по началу прятал бы строку от * того, кто набирает её собственное имя. * * `text` называет, где искать: у строки списка полей несколько, и по какому из * них её вспоминают, знает не этот файл, а тот, кто её показывает.
- отдаёт: matching

### state/sections.js (33)
- * Разделы в том порядке, в каком они стоят в меню. Значок — лигатура шрифта * `Material Symbols Outlined`.
- отдаёт: CONTACTS_TABS, PROFILE_TABS, SECTIONS, SYSTEM_TABS

### state/settings.js (222)
- * Чем подписано пустое поле имени модели. * * Пока имён нет, подсказка не обещает списка: перечень читается с адреса и * ключа, и у непóднятого поставщика его не будет вовсе — имя тогда вписывают * руками. Слова общие на настройки и на шаг мастера: одно и то же поле, * подписанное по-разному, читается как два разных.
- отдаёт: BOUNDS, CREDS_LIMITS, KEY_PLACEHOLDER, SAME_CREDS_LABEL, SCORE_MAX, blankCreds, blankTelegram, clampField, credsChanged, idleProbe, loginTrouble, mirrored, modelPlaceholder, nextStep, probePill, sameCreds, scorePercent, sessionPill, sessionText, telegramCreds, thresholdState

### state/skills.js (84)
- * Наибольший уровень навыка. Дорожка ползунка размечена по нему.
- отдаёт: aliasesAfter, countNote, grouped, groupsMatching, levelPercent

### state/stats.js (261)
- * Сроки, за которые считают, — от короткого к длинному. * * `delta` — как называется прирост за этот срок. У «всего времени» его нет: * сравнивать не с чем, это и есть всё время.
- отдаёт: KPI, PERIODS, STATUS_ORDER, convNote, deltaNote, donut, duration, kpiRow, skillRows, skillRowsPerColumn, sliceTarget, statusColumns, statusTotal, weekBars

### state/statuses.js (13)
- * Статусы в том порядке, в каком их читают в кольце статистики. * * Значение совпадает с тем, каким статус приходит в строке списка и каким его * принимает смена статуса на мосту; им же покрашена точка рядом.
- отдаёт: STATUS_CHOICES

### state/telegram.js (24)
- * Чем подписан ник — или прямое слово о том, что его нет. * * Отсутствие тут говорящее: такую запись не найти в Telegram по имени. Пустое * место читалось бы как недогрузившаяся строка.
- отдаёт: handleName, telegramHref

### state/unnamed.js (17)
- * Чем подписана запись без названия. Показывают её приглушённой * (`styles/unnamed.css`) — так видно, что это не название, а его отсутствие.
- отдаёт: UNNAMED

### state/vacancies.js (291)
- * Порядки списка в том виде, в каком их выбирают. Ключи уезжают на мост и * разбираются там `backend/repository/vacancies_list._order_for`; незнакомый * ему ключ сводится к «сначала новые». Первый здесь — тот, в котором список * открывается.
- отдаёт: SORTS, VACANCY_MODES, ago, blankVacancy, emptyNote, gradeLabel, remoteLabel, salaryLabel, scoreTone, shortAgo, shownStack, sortKey, typed, vacancyFields, vacancyLine, vacancyNamed

### state/vacancy_actions.js (55)
- * Почему отправка и переразбор сейчас недоступны. * * Пустая фраза значит «доступно». Обе просьбы уходят боту, поэтому неживое * окружение запирает оба и объясняется теми же словами, что и кнопка обхода * внизу окна: две разные фразы об одной беде человек читает как две беды. * * Отклик уходит человеку, и без привязанного HR слать его некому; разбору же * HR не нужен — он его как раз и находит.
- отдаёт: actionBlocks, rawChips

### state/vacancy_card.js (162)
- * Своя запись правится, чужая читается: пояснение бота — след его работы, а не * заметка, и правка стирала бы то, по чему потом разбираются.
- отдаёт: timelineRows

### state/vacancy_filter.js (193)
- * Грейды объявлены анкетой: значения те же — и туда, и сюда они ездят через * мост, а второе их написание разошлось бы с первым молча.
- отдаёт: COMPANY_MAX, DATE_PRESETS, GRADE_CHOICES, HR_CHOICES, REMOTE_CHOICES, activeCount, blankFilter, filterPayload, pickNames

### state/vacancy_view.svelte.js (34)
- * Отбор и порядок, какими их оставили в прошлый заход.
- отдаёт: vacancyView

### state/wizard.js (165)
- * Экраны по порядку. Приветствие и финал — обложки: шага у них нет, и в * строке шагов они ничего не подсвечивают.
- отдаёт: PRESETS, backScreen, cvModes, cvReady, llmTrouble, nextScreen, presetFor, resumeScreen, stepAt, stepMarks

### state/words.js (15)
- * Слово, согласованное с числом. * * «1 категории» человек читает как опечатку и перестаёт верить остальному на * экране. Числа 11–14 — исключение русского счёта и берут последнюю форму.
- отдаёт: plural

## styles — 103 файлов

### styles/accent-fill.css (16)
- Залито акцентом — так помечено выбранное и главное: основная кнопка окна, зажатая пилюля срока или рода, выбранный день в календаре. Одним правилом на три места, а не тремя одинаковыми: заливка здесь несёт один и тот же смысл «вот это», и разъедься её цвет или вес, соседние экраны стали бы помечать выбранное по-разному. Ввозится после оформления самих блоков: у их наведения та же весомость селектора, и выигрывает порядок.
- селекторы (1): .btn.primary,
.pill.active,
.date-day.selected
- берёт: --accent, --bg-primary

### styles/accent-outline.css (18)
- Обведено акцентом под курсором — так отзывается кнопка без своей заливки: добавить канал, добавить навык, добавить строку в отсев, обновить числа. Одним правилом на четыре места, а не четырьмя одинаковыми: отклик здесь несёт один и тот же смысл «нажмётся», и разъедься его цвет, соседние экраны отзывались бы по-разному. Заливка акцентом — про другое и живёт рядом, в accent-fill.css: там помечено выбранное, здесь отвечено на курсор. Кнопка заведения контакта сюда не сведена: у неё сверх обводки своя заливка, и правило у неё поэтому шире здешнего.
- селекторы (1): .bl-add-btn:hover,
.chip-add:hover,
.new-box:hover,
.stats-refresh-btn:hover
- берёт: --accent

### styles/add-channel.css (17)
- Окно заведения канала: узкая коробка с шапкой, полем и подвалом. Сами шапка, тело и подвал — общие, в modal.css.
- селекторы (2): .add-channel, .cnt-add-hint
- берёт: --text-tertiary

### styles/autosave-error.css (16)
- Отказ отложенной записи: коробка под формой вкладки анкеты. Стоит под формой, а не плашкой поверх экрана: анкету заполняют сверху вниз, и до последнего обязательного поля каждая запись законно отказана — плашка била бы на каждом поле. Рамкой и подложкой, а не голой строкой: строка под длинной формой теряется среди подписей полей.
- селекторы (1): .autosave-error
- берёт: --danger-border, --danger-wash, --err

### styles/bar.css (17)
- Полоса: ряд, отбитый снизу чертой и подложкой. Так стоят шапка окна, полоса над списком контактов и над списком вакансий, строка поиска в окне выбора. Полоса не прокручивается вместе с тем, что под ней: к ней возвращаются, пролистав список или дочитав текст. Своим файлом, а не в оформлении каждого места: форма у них одна и та же — четыре объявления из четырёх, — а различаются они просветом и отступами, потому что и содержимое разное: у шапки окна значок с заголовком, у полосы списка поле поиска и кнопки. Своё каждый и дописывает.
- селекторы (1): .bar
- берёт: --bg-tertiary, --border

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

### styles/blacklist-dialog.css (125)
- Окно заведения строки отсева: выбор рода, значение с подсказчиком и причина. Шапка, тело и подвал — общие, в modal.css.
- селекторы (18): .bl-add-modal,
.bl-add-modal .modal-body, .bl-kind-segmented, .bl-kind-seg, .bl-kind-seg:hover, .bl-kind-seg.active.keyword, .bl-kind-seg.active.hr, .bl-kind-seg.active.company, .bl-kind-seg.active.channel, .bl-modal-input,
.bl-modal-textarea, .bl-modal-textarea, .bl-combobox-wrap, .bl-combobox-dropdown, .bl-combobox-option, .bl-combobox-option:last-child, .bl-combobox-option:hover, .bl-combobox-option .opt-label, .bl-combobox-option .opt-sub, .bl-combobox-empty
- берёт: --bg-tertiary, --border, --fg-max, --kind-channel-active-bg, --kind-company-active-bg, --kind-hr-active-bg, --kind-keyword-active-bg, --selected-bg, --surface-raised, --text-primary, --text-secondary, --text-tertiary

### styles/blacklist.css (204)
- Чёрный список: полоса отбора и таблица строк под ней. Окно заведения строки — в blacklist-dialog.css.
- селекторы (27): .bl-toolbar, .bl-toolbar .search-box, .bl-filter-pills, .bl-filter-pill, .bl-filter-pill .count, .bl-add-btn, .bl-add-btn .material-symbols-outlined, .bl-table, .bl-row, .bl-row:last-child, .bl-row.head, .bl-row.head .bl-active-head, .bl-row:not(.head) > .bl-kind-chip,
.bl-row:not(.head) > .bl-input.value,
.bl-row:not(.head) > .bl-when,
.bl-row:not(.head) > .icon-btn, .bl-row > .toggle, .bl-row:not(.head) > .toggle, .bl-kind-chip, .bl-kind-chip.keyword, .bl-kind-chip.hr, .bl-kind-chip.company, .bl-kind-chip.channel, .bl-input, .bl-input:focus, .bl-input::placeholder, .bl-input.value, textarea.bl-input.reason, .bl-input.saved-flash, .bl-row.disabled .bl-input
- берёт: --bg-secondary, --bg-tertiary, --border, --info, --kind-channel-bg, --kind-channel-fg, --kind-company-bg, --kind-company-fg, --kind-hr-bg, --kind-keyword-bg, --kind-keyword-fg, --text-secondary, --text-tertiary

### styles/bullet-list.css (85)
- Список строк под заголовком: достижения и обязанности места работы. Своим файлом, а не в оформлении карточки: список этот — свой компонент, и стоять он может под любой формой. Строка в нём — многострочное поле, которое правится на месте: рамка и её отклик приходят из inline-edit.css.
- селекторы (12): .list-block .field-label, .list-add, .list-add:hover, .list-add .material-symbols-outlined, .list-item, .list-bullet, .list-input, .list-input:focus, .list-item .icon-btn, .list-item .icon-btn .material-symbols-outlined, .list-item:hover .icon-btn, .list-item button.icon-btn:hover
- берёт: --accent, --bg-secondary, --danger, --text-secondary, --text-tertiary

### styles/button.css (51)
- Кнопка с подписью. Значковые — в icon-button.css: у тех нет ни рамки, ни подложки, и общего с этими только сброс из base.css.
- селекторы (7): .btn, .btn:hover:not(:disabled), .btn.primary:hover:not(:disabled), .btn.danger, .btn.danger:hover:not(:disabled), .btn.text, .btn.text:hover:not(:disabled)
- берёт: --accent, --accent-hover-fill, --bg-tertiary, --border, --danger-btn, --err-btn-bg, --err-btn-bg-hover, --text-primary, --text-secondary

### styles/caption.css (22)
- Мелкая подпись капителью: она называет, а не читается наравне с названным. Одним правилом на все подписи, какие в окне есть: поле формы, шапка карточки чисел, шапка таблицы отсева, подпись числа в плитке канала, заголовок раздела в подборщике, подпись под кольцом. Приём один и тот же — приглушённый цвет, разрядка и капитель, — и написанный порознь, он расходится по мелочи: у одной подписи пропадает разрядка, и она читается плотнее соседних при том же кегле. Кегль остаётся при самих блоках: подписи в тесных местах мельче, и договориться об одном числе им не о чем.
- селекторы (1): .field-label,
.stats-card-title,
.bl-row.head,
.ch-stat-label,
.skill-picker-cat,
.donut-label
- берёт: --text-tertiary

### styles/card-section.css (18)
- Коробка блока в карточке. Так отделены друг от друга разделы правой панели: заметки, мини-списки, числа канала, стек вакансии, её описание и лента, переписка с человеком. Заголовков на панели нет, и без рамки блоки слились бы в одну простыню. Своим файлом, а не в оформлении каждой карточки: коробка была написана трижды — у контакта, у вакансии и у переписки, — и первые две совпадали всеми пятью объявлениями. Своё каждый блок дописывает сам: у переписки нет внутреннего отступа, потому что лента прижимается к рамке.
- селекторы (1): .card-section
- берёт: --bg-secondary, --border

### styles/channel-stats.css (79)
- Числа канала: четыре плитки и полоса воронки под ними. Полосой, а не кольцом: доли здесь читают одну относительно другой — сколько из собранного дошло до отклика, — и в ряд это видно, а по кругу нет. Цвет отрезков — общий набор из status-color.css.
- селекторы (12): .ch-stats-grid, .ch-stat, .ch-stat-num.fit, .ch-stat-num.apply, .ch-stat-num.response, .ch-stat-label, .ch-bar, .ch-bar-seg, .ch-bar-legend, .ch-bar-legend .legend-item, .ch-bar-legend .status-dot, .ch-stats-empty
- берёт: --accent, --bg-tertiary, --info, --status-applied, --text-secondary, --text-tertiary

### styles/chat.css (293)
- Переписка в карточке человека: лента писем, пузыри и строка отправки. Своим файлом, а не в оформлении карточки: карточку одевают три предмета, а переписка есть только у человека.
- селекторы (38): .cnt-detail-pane:has(> .cnt-chat-section), .cnt-chat-section, .cnt-chat-body, .cnt-chat-empty, .cnt-chat-day, .cnt-chat-older, .cnt-chat-older:hover, .cnt-bubble, .cnt-bubble.them, .cnt-bubble.me, .cnt-bubble.deleted, .cnt-bubble-content, .cnt-bubble-text, .cnt-bubble-text.deleted, .cnt-bubble-text.gone, .cnt-bubble-edited, .cnt-bubble-photo, .cnt-bubble-photo img, .cnt-bubble-doc, .cnt-bubble-doc:hover, .cnt-bubble-doc .material-symbols-outlined, .cnt-bubble-time, .cnt-bubble.me .cnt-bubble-time, .cnt-bubble-tick, .cnt-bubble-tick.read, .cnt-bubble.me .cnt-bubble-tick, .cnt-bubble.me .cnt-bubble-tick.read, .cnt-chat-input-area, .cnt-chat-input, .cnt-chat-input:focus, .cnt-chat-input::placeholder, .cnt-chat-attach, .cnt-chat-attach:hover:not(:disabled), .cnt-chat-attach .material-symbols-outlined, .cnt-chat-send, .cnt-chat-send:hover:not(:disabled), .cnt-chat-send .material-symbols-outlined, .cnt-chat-disabled-hint
- берёт: --accent, --accent-chip-bg, --accent-muted, --bg-tertiary, --border, --surface-raised, --surface-raised-hover, --text-primary, --text-secondary, --text-tertiary

### styles/checkbox.css (15)
- Галочка с подписью в одну строку: подпись нажимается вместе с квадратиком.
- селекторы (2): .checkbox-row, .checkbox-row input
- берёт: --accent, --text-secondary

### styles/chips.css (59)
- Короткие подписи россыпью: синонимы навыка, стек места работы.
- селекторы (7): .chips, .chip, .chip-x, .chip:hover .chip-x, .chip-add, .chip-input, .chip-input:focus
- берёт: --accent, --bg-secondary, --bg-tertiary, --border, --danger, --text-primary, --text-secondary, --text-tertiary

### styles/choice-row.css (80)
- Ряд вариантов выбора: два вида одного ряда. Сегментами — когда вариантов три-четыре и они делят ширину поровну; чипами — когда их одиннадцать и в один ряд равной ширины они не помещаются.
- селекторы (12): .choice-row, .choice, .choice:hover, .choice-row[data-look='seg'], .choice-row[data-look='seg'] .choice, .choice-row[data-look='seg'] .choice:first-child, .choice-row[data-look='seg'] .choice:last-child, .choice-row[data-look='seg'] .choice.active, .choice-row[data-look='seg'] .choice.active:hover, .choice-row[data-look='chip'], .choice-row[data-look='chip'] .choice, .choice-row[data-look='chip'] .choice.active
- берёт: --accent, --accent-chip-selected, --bg-secondary, --border, --surface-hover-firm, --surface-raised, --text-primary, --text-secondary

### styles/clipped-line.css (47)
- Строка в одну линию, обрезанная многоточием. Одним правилом на все места, где длинное значение не должно распирать свой столбец: имена в списках и карточках, подписи файлов, строки журнала, пилюли. Написанная в каждом файле оформления заново, эта тройка расходится молча — пропавший `white-space` даёт вторую строку и разъехавшуюся сетку, а пропавший `overflow` — обрезку без многоточия, по которой не видно, что значение длиннее показанного. Место, где строке отведена ширина, остаётся при самом блоке: `max-width`, `min-width: 0` и доля во флексе у каждого свои, и общими они не бывают. Хвост пилюли режется у самой подписи, а не у пилюли: обрезанная пилюля уносила бы вместе с хвостом и крестик, и длинную подпись стало бы нечем снять. Подписи бокового меню и имени категории третье объявление ничего не меняет: первая и так не переносится вслед за своей кнопкой, второе — поле ввода, где переноса не бывает вовсе. Держать их порознь ради этого значило бы писать ту же обрезку в третий и четвёртый раз.
- селекторы (1): .chip-text,
.hr-name,
.cnt-hr-name,
.cnt-hr-sub,
.pdf-name,
.exp-summary > strong,
.exp-summary > .role,
.file-pick .text,
.logs-source,
.logs-msg,
.vac-mini-title,
.hr-mini-name,
.picker-name,
.picker-sub,
.stats-ch-grid .stats-ch-name-cell,
.stats-skill-name,
.unread-popup-name,
.vac-title,
.vac-meta,
.status-label,
.nav-label,
.cat-name

### styles/collapse-arrow.css (21)
- Стрелка, которой сворачивают коробку: место работы и категорию навыков. Одним файлом на обе, а не по правилу в каждой коробке: знак у них один и тот же и поворачивается одинаково, а разъедься размер или скорость — две соседние вкладки анкеты сворачивались бы по-разному. Названа своим именем, а не «первым в шапке»: в шапке навыков стрелка обёрнута кнопкой, и отбор по месту клал бы набок кнопку вместо глифа — вместе с её отступами и мимо середины.
- селекторы (2): .collapse-arrow, .collapsed .collapse-arrow
- берёт: --text-secondary

### styles/collapsible.css (29)
- Коробка со сворачиваемой шапкой: категория навыков, место работы. Что внутри — своими файлами. Место работы названо здесь же: коробка у них одна и та же, а разошлась бы молча — первая же поправка досталась бы одной из двух. Своя у места работы только шапка, и живёт она в experience.css.
- селекторы (3): .collapsible,
.exp-card, .collapsible, .collapsible-head
- берёт: --bg-secondary, --bg-tertiary, --border

### styles/confirm-field.css (23)
- Поле, набранное в котором принимают отдельным нажатием: ввод и галочка в конце строки. Галочка стоит рядом с полем, а не в подвале окна: принимают ею набранное имя, а не форму целиком, и в подвале она читалась бы как второе «Создать». Показывается она только тогда, когда есть что принимать.
- селекторы (3): .confirm-field, .confirm-field .input, .confirm-field .icon-btn:hover
- берёт: --accent

### styles/contact-block.css (51)
- Кружок и два имени рядом с ним: так подписаны HR и компания в карточке вакансии и кандидаты в подборщике привязки.
- селекторы (7): .contact-block, .hr-avatar, .hr-avatar .material-symbols-outlined, img.hr-avatar, .hr-info, .hr-name, .hr-name.is-link:hover
- берёт: --accent, --bg-tertiary, --text-primary, --text-secondary

### styles/contact-card.css (116)
- Карточка контакта в правой панели: шапка, поля и коробки под ними. Одевает три карточки — человека, компании и канала: содержимое у них разное, а места этих мест одни. Переписка — в chat.css, мини-списки — в mini-list.css, числа канала — в channel-stats.css.
- селекторы (16): .cnt-det-head, .cnt-det-head > div, .cnt-det-head .hr-avatar, .cnt-det-name, .cnt-det-name.muted, .cnt-det-sub, .cnt-det-sub > *, .cnt-det-link, .cnt-det-link:hover, .cnt-det-meta-row, .cnt-det-meta-row > *, .cnt-det-meta-chip, .cnt-det-meta-chip.unread, .cnt-det-meta-chip.blacklist, .cnt-det-meta-chip .material-symbols-outlined, .cnt-input
- берёт: --accent, --accent-chip-bg, --bg-tertiary, --danger, --danger-tint-strong, --text-primary, --text-secondary, --text-tertiary

### styles/contacts-layout.css (42)
- Своё у вкладки контактов: кнопка заведения в полосе, два пустых состояния и подложка панели подробностей. Сама раскладка — общая с вакансиями, в master-detail.css: панели там прокручиваются раздельно и обе стоят на экране всегда — человека правят и пишут ему, не теряя из виду соседей по списку.
- селекторы (6): .cnt-add-btn, .cnt-add-btn:hover, .cnt-add-btn .material-symbols-outlined, .cnt-list-empty, .cnt-detail-pane, .cnt-detail-empty
- берёт: --accent, --border, --selected-bg

### styles/contacts.css (103)
- Строка списка контактов: кружок, имя с подписью и отметки в хвосте. Сами панели раздела — в contacts-layout.css, таблица отсева — в blacklist.css.
- селекторы (14): .cnt-hr-row, .cnt-hr-row .hr-avatar, .cnt-hr-info, .cnt-hr-name, .cnt-hr-sub, .cnt-hr-sub .at, .cnt-hr-sub .company, .cnt-hr-sub .sep, .cnt-hr-trailing, .cnt-hr-bl, .cnt-hr-bl .material-symbols-outlined, .cnt-hr-row.blacklisted .cnt-hr-name, .cnt-hr-unread, .cnt-co-count
- берёт: --accent, --bg-primary, --border, --danger, --text-primary, --text-secondary, --text-tertiary

### styles/count-pill.css (20)
- Тихая пилюля с числом в хвосте строки: счёт вакансий у компании и у канала, счёт в строке подборщика, оценка вакансии в списке и в мини-списке. Своим правилом, а не четырьмя одинаковыми у каждого списка: число здесь говорит, стоит ли открывать строку, но спорить за внимание с именем не должно — и решается это подложкой, кеглем и цифрами одной ширины. Написанное порознь, оно разошлось бы: у счёта и оценки уже разъехались отступы. Своё у каждой остаётся там же, где стоит: цвет числа у оценки говорит о пороге отбора, а отступы шире — у той пилюли, что стоит в широком окне.
- селекторы (1): .num-pill
- берёт: --bg-tertiary, --text-secondary

### styles/cv-file.css (40)
- Файл резюме: пунктирная рамка — то же, чем обычно показывают «сюда кладут».
- селекторы (6): .pdf-row, .pdf-row > .material-symbols-outlined, .pdf-info, .pdf-name, .pdf-meta, .pdf-actions
- берёт: --bg-secondary, --border, --danger, --text-primary, --text-tertiary

### styles/date-picker.css (97)
- Поле даты и сетка месяца под ним.
- селекторы (14): .date-picker, .input-date-text, .input-date-text.invalid, .date-panel, .date-panel.up, .date-head, .date-head .icon-btn:hover, .date-title, .date-week, .date-weekday, .date-cell, .date-day, .date-day:hover, .date-day.today
- берёт: --accent, --bg-tertiary, --err, --scrim, --selected-bg, --text-primary, --text-secondary

### styles/disabled-look.css (35)
- Как выглядит запертое: не даёт себя нажать и говорит об этом видом. Одним файлом на все места, где запертость показывают, — иначе одинаково запертые соседи гаснут по-разному, и разница читается как разная запертость. Глубин здесь три, и делит их не прихоть, а то, что заперто: — кнопка гаснет заметнее всех: она сплошная, и лёгкое приглушение на ней не читается; — пункт меню и карточка выбора приглушены мягче: они стоят в ряду таких же, и глубокая тень выбила бы ряд; — поле и кнопка отправки в переписке не гаснут вовсе, а гасят свои буквы: они и так на приглушённом полотне, а прозрачное поле читалось бы как пропавшее. Переключатель режима (`mode.css`) сюда не сведён: у него глубина своя и ни с одной из этих трёх не совпадает.
- селекторы (3): .btn:disabled,
.icon-btn.is-disabled,
.cnt-chat-attach:disabled, .menu-item.blocked,
.radio-card.disabled, .cnt-chat-input:disabled,
.cnt-chat-send:disabled
- берёт: --text-tertiary

### styles/donut.css (42)
- Кольцо долей: обводка круга сегментами и число в середине.
- селекторы (5): .donut-wrap, .donut, .donut-part, .donut-center, .donut-label
- берёт: --text-tertiary

### styles/dropdown.css (76)
- Выпадающий список со своим видом: системный в тёмном окне светлая заплата.
- селекторы (10): .cdd, .cdd-btn, .cdd-btn:hover,
.cdd.open .cdd-btn, .cdd-btn .material-symbols-outlined, .drop-panel, .pop-frame.drop-panel, .cdd-panel, .cdd-option, .cdd-option:hover, .cdd-option.active
- берёт: --accent, --bg-secondary, --border, --selected-bg, --shadow-dropdown, --text-primary, --text-secondary, --text-tertiary

### styles/empty-note.css (9)
- Надпись на месте пустого списка: почему здесь ничего нет. Одна на все экраны — журнал, настройки и те, что приедут следом.
- селекторы (1): .empty-note
- берёт: --text-tertiary

### styles/experience.css (117)
- Место работы: шапка карточки и всё, что внутри. Сама коробка — общая с категорией навыков, в collapsible.css; своя здесь шапка: там её нажимает одна стрелка, а здесь — вся строка целиком, и разложена она сеткой под стрелку, подпись и корзину.
- селекторы (15): .exp-header, .exp-card.collapsed .exp-header, .exp-summary, .exp-summary > strong, .exp-summary > .role, .exp-summary .period, .exp-delete, .exp-delete .material-symbols-outlined, .exp-body, .field-row .input, .date-pair, .date-pair .date-picker, .date-dash, .date-current, .date-current input
- берёт: --accent, --bg-tertiary, --border, --text-primary, --text-secondary, --text-tertiary

### styles/field-caption.css (26)
- Подпись поля в форме и строка, в которой она стоит перед полем. Не `.field-label` из caption.css: та набрана капителью, и так подписаны шапки таблиц, колонки чисел и заголовки разделов — там подпись одна на весь блок и стоит поодаль. В форме, где полей десяток, капитель читается громче самих полей, между которыми она и стоит. Перед полем, а не над ним: пилюли начинаются с той же строки, и подпись читается как её начало, а не как заголовок над пустотой.
- селекторы (3): .field-caption, .captioned-field, .captioned-field .chips
- берёт: --text-tertiary

### styles/field-line.css (14)
- Несколько полей одной строкой: вилка «от — до — валюта», страна и город. Не сетка формы (`form-grid.css`): та делит ряд на две равные колонки, а здесь полей бывает три и ширина у них разная — знак валюты уже числа.
- селекторы (2): .field-line, .field-line > *

### styles/file-pick.css (35)
- Выбор файла резюме: одна строка со значком, подписью и кнопкой. Пунктир до выбора говорит «сюда кладут», сплошная рамка после — что файл уже взят: пустая строка со сплошной рамкой читалась бы как поле, в которое забыли что-то вписать.
- селекторы (5): .file-pick, .file-pick.has-file, .file-pick .material-symbols-outlined, .file-pick .text, .file-pick .text .name
- берёт: --bg-tertiary, --border, --text-primary, --text-secondary, --text-tertiary

### styles/filter-group.css (18)
- Группа отбора: подпись над своими полями и черта под ними.
- селекторы (3): .filter-group, .filter-group:last-child, .filter-label
- берёт: --border, --text-tertiary

### styles/footer.css (40)
- Рама нижней полосы: три её места и то, как они делят ширину. Что стоит внутри — лампочки, режим, ход обхода, счётчик — своими файлами.
- селекторы (4): .bottom-bar, .bb-left, .bb-right, .bb-center
- берёт: --bg-secondary, --border

### styles/form-grid.css (47)
- Сетка формы: два поля в ряд, и место на всю ширину для тех, кому двух колонок мало. Так стоят четыре формы окна: анкета, поля карточки контакта, место работы и настройки. Написаны они были порознь, и правило «занять оба столбца» — под тремя из четырёх: у карточки контакта широких полей сегодня нет, и правила ей не заведено. Своё у каждой формы одно: просвет между полями. Он и правда разный — в тесной панели карточки поля стоят плотнее, чем на просторной вкладке.
- селекторы (7): .form-grid,
.cnt-form-grid,
.field-row,
.settings-row, .form-grid .span-2,
.field-row .span-2,
.settings-row .span-2, .field-label, .form-grid, .cnt-form-grid, .field-row, .settings-row

### styles/health-lamp.css (34)
- Лампочка состояния: точка и короткое имя под ней.
- селекторы (5): .health, .health .dot, .health[data-state='ok'] .dot, .health[data-state='err'] .dot, .health-label
- берёт: --accent, --accent-glow-inner, --accent-glow-outer, --err, --err-glow-inner, --err-glow-outer, --text-secondary, --text-tertiary

### styles/help-block.css (34)
- Пошаговая инструкция «где это взять»: нумерованный список с адресами. Стоит под полем, которое сама и объясняет: api_id в мастере Telegram, адрес поставщика моделей.
- селекторы (5): .help, .help strong, .help code, .help ol, .help ol li
- берёт: --bg-tertiary, --text-primary, --text-secondary

### styles/icon-button.css (29)
- Кнопка-значок: квадрат со значком внутри, без подписи. Вынесена на втором потребителе — кнопка обхода в полосе и очистка журнала.
- селекторы (4): .icon-btn, .icon-btn .material-symbols-outlined, .icon-btn:hover, .icon-btn.is-disabled:hover
- берёт: --bg-tertiary, --text-primary, --text-secondary

### styles/inline-edit.css (41)
- Поле, которое правится на месте. Так набирают там, где поле стоит внутри чужого блока и формой быть не должно: значение и причина в таблице отсева, пояснение в ленте вакансии, строка достижения, имя категории и имя навыка. Рамки у такого поля в покое нет — иначе список из полусотни строк читался бы анкетой, — она проступает под курсором и светится акцентом в наборе. Своим файлом, а не пятью записями по блокам: правило наведения было переписано побайтно пять раз. Каждый блок оставляет себе только своё — размер, начертание, то, как поле тянется, и подложку набора: она у них разная, потому что разный фон под самим полем. Рамка набора не гаснет под курсором: наводят как раз на то поле, в котором набирают, и правило наведения без этой оговорки перебивало бы её — так уже случилось у имени навыка.
- селекторы (4): .inline-edit, .inline-edit:hover:not(:focus), .inline-edit:focus, .inline-edit.saved-flash,
.inline-edit.saved-flash:hover
- берёт: --accent, --border, --text-primary

### styles/input.css (83)
- Поле ввода, многострочное поле и поле для секрета рядом с глазом. Экран настроек уменьшает их своим правилом — там полей вдвое больше.
- селекторы (10): .input,
.textarea, .input:hover:not(:disabled, :focus),
.textarea:hover:not(:disabled, :focus), .input:focus,
.textarea:focus, .input::placeholder,
.textarea::placeholder, .textarea, .textarea.grown, .secret-input, .secret-input .input, .input.missing:not(:focus), .input.mono
- берёт: --accent, --bg-secondary, --border, --danger-border, --danger-wash, --text-primary, --text-secondary, --text-tertiary

### styles/lang-rows.css (49)
- Языки анкеты: строка на язык и кнопка добавления под списком.
- селекторы (8): .lang-list, .lang-row, .lang-row .input, .lang-row .cdd-label,
.lang-row .cdd-option, .lang-remove, .lang-remove:hover, .lang-add, .lang-add:hover
- берёт: --accent, --danger, --text-secondary, --text-tertiary

### styles/log-level-pill.css (67)
- Пилюля уровня: значок, имя и счёт записей этого уровня во всём буфере. Цвет зажатой берётся по тону, и тон тот же, что у уровня в строке списка (`log-row.css`): разойдись они, красная строка стояла бы под жёлтой пилюлей.
- селекторы (10): .logs-level-pill, .logs-level-pill .material-symbols-outlined, .logs-level-pill:hover, .logs-level-pill .count, .logs-level-pill.active .material-symbols-outlined, .logs-level-pill.active .count, .logs-level-pill.active[data-tone='error'], .logs-level-pill.active[data-tone='warn'], .logs-level-pill.active[data-tone='info'], .logs-level-pill.active[data-tone='debug']
- берёт: --accent, --alert-fill, --alert-muted, --alert-text, --bg-secondary, --bg-tertiary, --border, --danger, --err-fill, --err-muted, --info, --info-fill, --info-muted, --text-primary, --text-secondary, --text-tertiary

### styles/log-row.css (61)
- Строка журнала: время, уровень, источник, сообщение — и трассировка под ними, когда строку развернули.
- селекторы (12): .logs-row, .logs-row.expanded, .logs-time, .logs-level, .logs-level[data-tone='error'], .logs-level[data-tone='warn'], .logs-level[data-tone='info'], .logs-level[data-tone='debug'], .logs-source, .logs-msg, .logs-row.expanded .logs-msg, .logs-details
- берёт: --alert-text, --bg-secondary, --bg-tertiary, --border, --danger, --info, --text-primary, --text-secondary, --text-tertiary

### styles/logs.css (39)
- Экран журнала: панель сверху и список записей под ней. Что стоит внутри — пилюли и строки — своими файлами.
- селекторы (5): .logs-toolbar, .logs-level-pills, .logs-toolbar-gap, .logs-auto-refresh, .logs-list

### styles/master-detail.css (71)
- Каркас «список слева, подробности справа» — общий у контактов и вакансий. Своим файлом, потому что раскладка одна на два раздела, а написана была дважды: под приставкой `cnt-` и под `vac-`. Ширина панели стояла двумя числами в двух файлах, и разъехались бы они молча — а разделы эти стоят соседними вкладками одного окна, и разницу видно глазом. Селекторы сгруппированы, а не сведены к общему имени: имена классов несущие — по ним разметка и оформление раздела ищутся поиском, — и переименование стоило бы дороже, чем даёт. Что осталось у каждого раздела своим: отступы подробностей (у вакансий они плотнее — строка там гуще), пустые состояния (у вакансий это центрованный столбик со значком, у контактов простой абзац) и всё содержимое строки.
- селекторы (6): .cnt-layout,
.vacancies-layout, .cnt-list-pane,
.vac-list-pane, .cnt-list-toolbar,
.vac-list-toolbar, .cnt-list,
.vac-list, .cnt-detail-pane,
.vac-detail-pane, .cnt-hr-row.selected,
.vac-row.selected
- берёт: --accent, --bg-primary, --bg-secondary, --border, --selected-bg

### styles/matched-chip.css (15)
- Совпавшее с анкетой подсвечено: по нему решают, стоит ли открывать. Своим файлом, а не двумя правилами: чипов таких два — стек в карточке вакансии и стек в её строке списка, — и подсветка у них одна. Разойдись она, совпавшее в списке читалось бы иначе, чем в карточке, куда человек по нему и открыл. Ввозится после обоих чипов нарочно: вес у отметки и у самого чипа один и тот же, и решает порядок — ввези её раньше, и чип закрасил бы подсветку своей подложкой.
- селекторы (1): .matched
- берёт: --accent, --accent-chip-bg

### styles/menu.css (67)
- Меню действий: что стоит внутри списка под кнопкой-значком. Оправа окошка — общая, в popover.css.
- селекторы (10): .menu, .menu-item, .menu-item:hover, .menu-item .material-symbols-outlined, .menu-item.blocked,
.menu-item.blocked .material-symbols-outlined, .menu-item.blocked:hover, .menu-item.danger,
.menu-item.danger .material-symbols-outlined, .menu-item.danger:hover, .menu-item.danger:hover,
.menu-item.danger:hover .material-symbols-outlined, .menu-line
- берёт: --border, --danger, --danger-hover-fg, --danger-tint, --selected-bg, --text-primary, --text-secondary, --text-tertiary

### styles/mini-list.css (97)
- Нажимаемая строка внутри карточки контакта: вакансия и человек компании. Обе ведут отсюда наружу — к вакансии и к карточке человека, — и поэтому одеты одинаково: подсветка при наведении и имя, загорающееся акцентом, говорят, что по строке нажимают. Коробка вокруг них общая, в contact-card.css.
- селекторы (14): .vacs-mini,
.hrs-mini, .vac-mini-row,
.hr-mini-row, .vac-mini-row, .hr-mini-row, .vac-mini-row:first-child,
.hr-mini-row:first-child, .vac-mini-row:hover,
.hr-mini-row:hover, .vac-mini-row:hover .vac-mini-title,
.hr-mini-row:hover .hr-mini-name, .vac-mini-score, .vac-mini-title,
.hr-mini-name, .hr-mini-row .hr-avatar, .hr-mini-meta, .hr-mini-go, .mini-list-empty, .mini-list-more
- берёт: --accent, --border, --selected-bg, --text-primary, --text-tertiary

### styles/modal.css (194)
- Окно поверх окна: затемнение на весь экран и коробка по центру.
- селекторы (23): .modal-backdrop, .modal-dialog, .modal-dialog.narrow, .modal-dialog.narrow.tall, .modal-dialog.narrow .modal-body, .modal-dialog.narrow .modal-body > *, .modal-message, .modal-title, .modal-title .material-symbols-outlined, .modal-head, .modal-head .modal-title, .modal-head > .material-symbols-outlined, .modal-title-meta, .modal-close, .modal-close:hover, .modal-close .material-symbols-outlined, .modal-body, .modal-actions,
.modal-footer, .modal-footer, .modal-footer .btn, .modal-footer .btn .material-symbols-outlined, .modal-subtitle, .modal-error
- берёт: --bg-secondary, --bg-tertiary, --border, --danger, --scrim, --shadow-modal, --text-primary, --text-secondary, --text-tertiary

### styles/mode.css (50)
- Переключатель режима бота: слово, дорожка и бегунок на ней.
- селекторы (13): .mode-control, .mode-text, .mode-track, .mode-knob, .mode-control[data-mode='Off'] .mode-knob, .mode-control[data-mode='Off'] .mode-text, .mode-control[data-mode='Off'] .mode-track, .mode-control[data-mode='DM Only'] .mode-knob, .mode-control[data-mode='DM Only'] .mode-text, .mode-control[data-mode='DM Only'] .mode-track, .mode-control[data-mode='Full'] .mode-knob, .mode-control[data-mode='Full'] .mode-text, .mode-control[data-mode='Full'] .mode-track
- берёт: --accent, --accent-muted, --bg-tertiary, --border, --err, --err-muted, --text-secondary, --text-tertiary, --warn, --warn-muted

### styles/nav.css (92)
- Боковое меню: разделы и кнопка разворота.
- селекторы (14): .sidebar, .nav-group,
.sidebar-toggle, .nav-group, .nav-icon-rail, .nav-icon-rail .material-symbols-outlined, .nav-label, .app-frame:not(.sidebar-expanded) .nav-label, .nav-group:hover, .nav-group.active, .nav-group.active .nav-icon-rail .material-symbols-outlined, .sidebar-spacer, .sidebar-toggle, .sidebar-toggle:hover, .sidebar-toggle .material-symbols-outlined
- берёт: --accent, --bg-tertiary, --border, --rail-w, --selected-bg, --text-primary, --text-secondary, --text-tertiary

### styles/new-box.css (24)
- Пунктирная кнопка «завести ещё»: пустая коробка во всю ширину под уже заведёнными. Пунктиром, потому что содержимого у неё ещё нет: сплошная рамка читалась бы как очередная запись, в которой ничего не показали. Своим файлом, а не в оформлении каждой вкладки: так заводят категорию навыков и место работы, и написана она была дважды — уже разойдясь курсором и способом показа.
- селекторы (1): .new-box
- берёт: --border, --text-tertiary

### styles/note-card.css (51)
- Две карточки-подсказки: предупреждение и пояснение. Устроены одинаково, различаются цветом и значком: на них смотрят прежде текста, и цвет говорит, беда это или объяснение. Стоят они в мастере — там, где человеку надо сказать больше строки, но меньше, чем отдельным шагом.
- селекторы (7): .warning-card,
.info-card, .warning-card, .warning-card .material-symbols-outlined, .warning-card strong, .info-card, .info-card .material-symbols-outlined, .info-card strong
- берёт: --alert-card-bg, --alert-card-border, --alert-text, --info, --info-card-bg, --info-card-border, --text-primary

### styles/notes-area.css (31)
- Заметка к вакансии и вспышка «записано». Вспышка тут же, а не в оформлении заметки: ею отзывается и пояснение в ленте, а правило у неё одно — зелёная рамка с ореолом на те же доли секунды.
- селекторы (3): .notes-area, .notes-area:focus, .saved-flash,
.saved-flash:focus
- берёт: --accent, --accent-flash, --accent-focus-ring, --bg-tertiary

### styles/palette.css (195)
- Палитра приложения: единственное место, где цвет записан значением, — всё остальное оформление берёт его через var(), и это держит хук. Собрана сплошным вычитыванием обоих <style> прежней разметки (`main.html` и `wizard.html`, снесены слайсом В1): 237 записей литералами, 104 различных цвета. Оттенки не сведены и не подправлены — близкие, но разные пары оставлены разными, потому что разницу видно на экране.
- селекторы (1): :root
- объявляет: --accent, --accent-badge-hover, --accent-chip-bg, --accent-chip-selected, --accent-flash, --accent-focus-ring, --accent-glow-inner, --accent-glow-outer, --accent-hover-faint, --accent-hover-fill, --accent-hover-soft, --accent-muted, --accent-option-active, --accent-row-current, --accent-row-hover, --alert, --alert-card-bg, --alert-card-border, --alert-fill, --alert-muted, --alert-text, --bg-over-content, --bg-primary, --bg-secondary, --bg-tertiary, --border, --danger, --danger-border, --danger-btn, --danger-hover-fg, --danger-tint, --danger-tint-strong, --danger-toast-bg, --danger-toast-fg, --danger-wash, --dot-outline, --err, --err-btn-bg, --err-btn-bg-hover, --err-fill, --err-fill-strong, --err-glow-inner, --err-glow-outer, --err-muted, --err-stop-hover, --err-zone-bg, --err-zone-border, --fg-max, --info, --info-card-bg, --info-card-border, --info-fill, --info-muted, --kind-channel-active-bg, --kind-channel-bg, --kind-channel-fg, --kind-company-active-bg, --kind-company-bg, --kind-company-fg, --kind-hr-active-bg, --kind-hr-bg, --kind-keyword-active-bg, --kind-keyword-bg, --kind-keyword-fg, --ok, --ok-fill, --ok-text, --score-warn, --scrim, --selected-bg, --shadow-dropdown, --shadow-modal, --shadow-popup, --shadow-soft, --stats-group-funnel, --stats-group-ingest, --stats-group-outcome, --status-applied, --status-not-fit, --status-not-fit-timeline, --status-offer, --status-test, --surface-hover-firm, --surface-raised, --surface-raised-hover, --text-primary, --text-secondary, --text-tertiary, --tl-halo-answered, --tl-halo-applied, --tl-halo-decline, --tl-halo-default, --tl-halo-ghosting, --tl-halo-in-progress, --tl-halo-invitation, --tl-halo-new, --tl-halo-not-fit, --tl-halo-offer, --tl-halo-scam, --tl-halo-test, --warn, --warn-glow-inner, --warn-glow-outer, --warn-muted

### styles/pick-list.css (61)
- Выбор многих из длинного перечня: кнопка со счётом и раскрывающаяся панель с поиском под ней. Выпадающий список одного значения — в dropdown.css.
- селекторы (7): .pick, .pick-btn, .pick-btn .material-symbols-outlined, .pick-panel, .pick-list, .pick-list .checkbox-row, .pick-list .empty-note
- берёт: --bg-tertiary, --border, --shadow-dropdown, --text-primary, --text-tertiary

### styles/picker.css (127)
- Окно выбора: полоса поиска, список кандидатов и строка заведения под ним. Шапка, тело и подвал — общие, в modal.css; кружок с именами — в contact-block.css.
- селекторы (20): .vac-picker-modal, .picker-search-bar, .picker-search-bar .search-input, .picker-list, .picker-empty, .picker-row, .picker-row.selected, .picker-row.current, .picker-row.current .picker-name, .picker-row.blocked, .picker-info, .picker-name, .picker-current-mark, .picker-sub, .picker-meta, .vac-count, .picker-create, .picker-create-toggle, .picker-create-toggle:hover, .picker-create-toggle .material-symbols-outlined
- берёт: --accent, --accent-hover-faint, --accent-row-current, --bg-tertiary, --border, --selected-bg, --text-primary, --text-secondary, --text-tertiary

### styles/pill.css (20)
- Пилюля выбора: нажимаемая скобка, одна из ряда. Ею выбирают род строки в чёрном списке и срок в статистике. Выбранная залита акцентом целиком, а не подсвечена рамкой: пилюль в ряду пять, и приглушённой отметки среди них глаз не находит.
- селекторы (2): .pill, .pill:hover
- берёт: --accent, --bg-secondary, --border, --text-secondary

### styles/pipeline.css (70)
- Пороги отбора: пять величин в ряд, ползунок, числовые поля и тумблер.
- селекторы (9): .pipeline-row, .pipeline-row > div, .pipeline-label, .with-unit, .with-unit .input, .with-unit .unit, .slider-row, .slider-num, .with-toggle
- берёт: --text-secondary, --text-tertiary

### styles/plaque.css (36)
- Плашка отказа: одна на всё окно, поверх чего угодно.
- селекторы (3): .app-toast, .app-toast.visible, .app-toast.danger
- берёт: --bg-secondary, --border, --danger, --danger-toast-bg, --danger-toast-fg, --shadow-soft, --text-primary

### styles/popover.css (28)
- Окошко под кнопкой: общая оправа всплывающих панелей. Своё у каждой — сторона, к которой она прижата, ширина и то, что внутри; общее — то, чем она отделена от страницы под собой.
- селекторы (3): .pop-wrap, .pop,
.pop-frame, .pop
- берёт: --bg-secondary, --border, --shadow-popup

### styles/progress.css (61)
- Ход обхода: две полосы и подпись рядом с ними.
- селекторы (7): .bb-center .progress-wrap, .progress-bars, .progress-caption, .progress-bar, .progress-fill, .progress-bar[data-indeterminate='true'] .progress-fill, @keyframes slide
- берёт: --accent, --bg-tertiary, --text-secondary

### styles/quiet-number.css (14)
- Тихое число в хвосте строки: давность и уровень. Одним правилом, потому что читают его последним и одинаково — приглушённым, мельче соседей и моноширинными цифрами. Цифры моноширинные не для красоты: числа стоят одно под другим, и пропорциональные дёргали бы хвост строки от записи к записи.
- селекторы (1): .bl-when,
.vac-mini-when,
.skill-picker-item .lvl
- берёт: --text-tertiary

### styles/radio-card.css (51)
- Карточка выбора: способ, его название и пояснение под ним. Карточками, а не строкой переключателей: у каждого способа есть пояснение, и в строку оно не встаёт. Так выбирают, что делать с резюме.
- селекторы (8): .radio-card, .radio-card:hover, .radio-card.selected, .radio-card.disabled:hover, .radio-card input, .radio-card.disabled input, .radio-card .rc-title, .radio-card .rc-sub
- берёт: --accent, --accent-hover-soft, --bg-tertiary, --border, --text-primary, --text-tertiary

### styles/raw-text.css (80)
- Окно исходного текста: полоса сведений об объявлении и сам текст под ней. Шапка, тело и крестик — общие, в modal.css.
- селекторы (9): .vac-raw-modal, .raw-meta, .raw-meta-chip, .raw-meta-chip .material-symbols-outlined, .raw-copy-btn, .raw-copy-btn:hover, .raw-copy-btn:active, .raw-copy-btn .material-symbols-outlined, .raw-text
- берёт: --accent, --bg-over-content, --bg-secondary, --bg-tertiary, --border, --text-primary, --text-secondary

### styles/row-hover.css (26)
- Строка под курсором подсвечена — так видно, куда попадёт нажатие. Одним правилом на все перечни: строки отсева, контактов, журнала, подборщика, навыков и вакансий. Отклик этот значит одно и то же везде, и написанный порознь, он разъезжается на глаз — в одном списке строка отзывается, в соседнем нет, и человек решает, что она не нажимается. Само значение держит переменная (`palette.css`), так что цвет тут и так был бы один; своим файлом сведено объявление — чтобы новый перечень получал отклик, а не переписывал его седьмой раз. Строки, у которых своя подложка означает положение дел, из отклика исключены поимённо: шапка таблицы отсева, развёрнутая запись журнала, выбранный и нынешний в подборщике, отмеченная строка контактов и вакансий. Подсветить их значило бы стереть с них ответ на вопрос, ради которого подложку и красили: отклик тусклее отметки, и наведение на выбранную строку выглядело бы её снятием.
- селекторы (1): .bl-row:hover:not(.head),
.cnt-hr-row:hover:not(.selected),
.logs-row:hover:not(.expanded),
.picker-row:hover:not(.selected):not(.current),
.skill-row:hover,
.vac-row:hover:not(.selected)
- берёт: --accent-row-hover

### styles/ruled-row.css (11)
- Строка перечня, отделённая чертой сверху: строка навыка в анкете и строка навыка в карточке статистики. Общее у них — сетка, выравнивание по средней линии и сама черта; колонки, зазор, отступ и размер шрифта у каждой свои: одну правят, вторую читают.
- селекторы (1): .ruled-row
- берёт: --border

### styles/run.css (26)
- Кнопка обхода: пуск и остановка одним значком. Общее с прочими кнопками-значками — в icon-button.css.
- селекторы (3): .run-btn::before, .run-btn[data-running='true']::before, .run-btn[data-running='true']:hover
- берёт: --err, --err-stop-hover, --ok

### styles/screen.css (37)
- Общее у экранов раздела: шапка с заголовком и поле под вкладками.
- селекторы (6): .screen-body, .screen-body.flush, .page-head, .page-title, .page-title-meta, .updated-ts
- берёт: --text-primary, --text-tertiary

### styles/scroll-body.css (23)
- Тело, которое занимает остаток рамы и прокручивается внутри себя. Одним правилом на все места, где прокручивается середина, а не окно целиком: у экрана раздела, у страницы настроек, у тела окна, у панели отбора и у перечня подборщика шапка и подвал обязаны остаться на виду. `min-height: 0` тут не украшение: без него флексовый ребёнок не сжимается ниже своего содержимого, тело распирает раму, и прокрутки не выходит вовсе. Написанная в каждом файле заново, эта четвёрка и расходится обычно на нём — молча и с виду беспричинно. Отступы и подложка остаются при самих блоках: они у каждого свои.
- селекторы (1): .screen-body,
.settings-page,
.modal-body,
.filter-body,
.picker-list

### styles/search-box.css (65)
- Строка поиска над списком: лупа, поле и крестик очистки. Своим файлом, а не в оформлении списка: коробка одна на всё окно — вакансии, четыре вкладки контактов, окно выбора записи и подборщик навыков, — и различает их только место, в котором она стоит.
- селекторы (8): .search-box, .search-box .material-symbols-outlined, .search-input, .search-input:focus, .search-clear, .search-clear:hover, .search-clear .material-symbols-outlined, .search-bar .search-box
- берёт: --surface-hover-firm, --text-primary, --text-secondary, --text-tertiary

### styles/settings-section.css (69)
- Коробка с заголовком-шапкой: секция настроек и карточка чисел. Имя осталось от первого потребителя — переименование задело бы три файла ради одного слова.
- селекторы (10): .settings-section,
.stats-card, .settings-section, .settings-section-title, .settings-section-title .material-symbols-outlined, .settings-section.danger, .settings-section.danger .settings-section-title,
.settings-section.danger .settings-section-title .material-symbols-outlined, .danger-row, .danger-text, .danger-sub, .danger-row .btn
- берёт: --bg-secondary, --border, --danger, --err-zone-bg, --err-zone-border, --text-primary, --text-secondary, --text-tertiary

### styles/settings.css (89)
- Экран настроек: колонка секций посреди поля. Что внутри секций — сетка полей, пороги, опасная зона — своими файлами.
- селекторы (12): .settings-page, .settings-inner, .settings-page .input, .settings-page .btn, .settings-page .btn .material-symbols-outlined, .settings-page .btn.danger, .settings-page .btn.danger:hover:not(:disabled), .settings-row.spaced, .settings-actions, .session-actions, .session-row, .session-info
- берёт: --bg-tertiary, --border, --danger, --text-tertiary

### styles/shell.css (42)
- Рама окна: боковое меню, поле раздела, нижняя полоса. Раскладка сеткой, и разворот меню — это правка одной её переменной.
- селекторы (4): .app-frame, .app-frame.sidebar-expanded, .main, .placeholder-content
- объявляет: --footer-h, --rail-w, --sidebar-w
- берёт: --bg-primary, --bg-secondary, --footer-h, --rail-w, --sidebar-w, --text-tertiary

### styles/skill-picker.css (92)
- Стек места работы: чипы взятых навыков и подборщик под ними. Своим файлом, а не в оформлении карточки: подборщик — свой компонент, и выбирают им из навыков анкеты, а не из чего-то, что знает карточка.
- селекторы (12): .skills-block, .skill-picker, .skill-picker-search, .skill-picker-search .search-input, .skill-picker-search > .search-box > .material-symbols-outlined, .skill-picker-list, .skill-picker-cat, .skill-picker-item, .skill-picker-item:hover, .skill-picker-item.disabled, .skill-picker-item.disabled:hover, .skill-picker-empty
- берёт: --border, --selected-bg, --shadow-dropdown, --text-primary, --text-tertiary

### styles/skills.css (103)
- Навыки: строка навыка внутри категории. Сама коробка категории — общая, в collapsible.css.
- селекторы (14): .cat-name, .cat-name:focus, .cat-spacer, .cat-add, .cat-add:hover, .cat-add .material-symbols-outlined, .cat-delete, .cat-delete .material-symbols-outlined, .skill-row, .skill-row .icon-btn .material-symbols-outlined, .skill-name, .skill-name:focus, .level, .level-num
- берёт: --accent, --bg-secondary, --text-secondary, --text-tertiary

### styles/slider.css (80)
- Ползунок: порог отбора в настройках, уровень навыка в анкете. Заливка дорожки нарисована фоном самого поля: у ползунка нет своей «пройденной» части, а два элемента поверх друг друга разъезжались бы на краях. Долю кладёт разметка переменной `--pct`.
- селекторы (7): input[type='range'].slider, input[type='range'].slider::-webkit-slider-runnable-track, input[type='range'].slider::-moz-range-track, input[type='range'].slider::-webkit-slider-thumb, input[type='range'].slider::-moz-range-thumb, input[type='range'].slider:active::-webkit-slider-thumb,
.slider-row:hover input[type='range'].slider::-webkit-slider-thumb,
.skill-row:hover input[type='range'].slider::-webkit-slider-thumb, input[type='range'].slider:active::-moz-range-thumb,
.slider-row:hover input[type='range'].slider::-moz-range-thumb,
.skill-row:hover input[type='range'].slider::-moz-range-thumb
- берёт: --accent, --bg-tertiary, --pct

### styles/spin.css (12)
- Вращение значка: им показано, что дело идёт и ответа ещё нет. Своим файлом, а не в оформлении каждого экрана: крутится значок в двух местах — кнопка пересчёта статистики и строка состояния шага мастера, — и объявлено вращение было дважды, под двумя именами. Скорость у них при этом разная, и это своё: у кнопки оборот быстрее, потому что и ждать её недолго.
- селекторы (1): @keyframes spin

### styles/stats-channels.css (140)
- Карточка «Каналы»: воронка канала одиннадцатью колонками. Сеткой, а не таблицей: имя канала и колонки конверсии резиновые, числовые — узкие по содержимому, и только так все одиннадцать влезают в карточку без поперечной прокрутки. Группы «Ингест», «Воронка отклика» и «Конверсия» отделены тонкой чертой — без неё одиннадцать чисел читаются как один ряд.
- селекторы (24): .stats-ch-grid, .stats-ch-grid > *, .stats-ch-grid .stats-ch-group, .stats-ch-grid .stats-ch-group, .stats-ch-grid .stats-ch-group.ingest, .stats-ch-grid .stats-ch-group.funnel, .stats-ch-grid .stats-ch-group.outcome, .stats-ch-grid .stats-ch-th, .stats-ch-grid .stats-ch-name-cell, .stats-ch-grid .stats-ch-th-name, .stats-ch-grid .stats-ch-sep-l, .stats-ch-grid .stats-ch-conv, .stats-ch-grid .stats-ch-conv-label, .stats-ch-grid .stats-ch-conv-meter, .stats-ch-grid .stats-ch-conv-meter-fill, .stats-ch-grid .stats-ch-row, .stats-ch-grid .stats-ch-row.is-hover, .stats-ch-grid .v-dim, .stats-ch-grid .v-fit, .stats-ch-grid .v-sent, .stats-ch-grid .v-answ, .stats-ch-grid .v-invite, .stats-ch-grid .v-decline, .stats-ch-grid .stats-ch-last
- берёт: --accent, --bg-tertiary, --border, --cols, --err, --info, --stats-group-funnel, --stats-group-ingest, --stats-group-outcome, --status-applied, --surface-raised, --text-primary, --text-secondary, --text-tertiary

### styles/stats-responses.css (84)
- Карточка «Ответы HR»: столбцы по дням недели и две метрики под ними. Столбцы сверху, метрики снизу за чертой: график — то, ради чего в карточку смотрят, а метрики его подписывают.
- селекторы (11): .stats-resp-card, .stats-resp-chart, .stats-resp-bar-wrap, .stats-resp-bar-num, .stats-resp-bar, .stats-resp-bar.weekend, .stats-resp-bar-label, .stats-resp-stats, .stats-resp-stat-num, .stats-resp-stat-num.dim, .stats-resp-stat-label
- берёт: --accent, --alert, --border, --text-primary, --text-secondary, --text-tertiary

### styles/stats-skills.css (107)
- Карточка «Скилы»: навыки вакансий тремя колонками с полосой частоты. Полоса, а не одно число: по ней видно, во сколько раз первый навык встречается чаще пятого, — а это и есть то, ради чего в карточку смотрят.
- селекторы (15): .stats-skills-grid, .stats-skill-row, .stats-skill-row.first-in-col, .stats-skill-check, .stats-skill-name, .stats-skill-row:not(.mine) .stats-skill-name, .stats-skill-bar, .stats-skill-bar-fill, .stats-skill-row.mine .stats-skill-bar-fill,
.stats-skills-legend .leg-mine, .stats-skill-row:not(.mine) .stats-skill-bar-fill,
.stats-skills-legend .leg-other, .stats-skill-row.mine .stats-skill-bar-fill, .stats-skill-num, .stats-skills-legend, .stats-skills-legend span, .stats-skills-legend .leg-dot
- берёт: --accent, --bg-tertiary, --border, --text-primary, --text-secondary, --text-tertiary

### styles/stats-status.css (55)
- Карточка «Статусы»: счётчики двумя колонками и кольцо между ними. Само кольцо — в donut.css, цвет точки — в status-color.css.
- селекторы (7): .stats-status-card, .stats-status-col, .stats-status-col.right, .stats-sc-item, .stats-sc-item:hover, .stats-sc-name, .stats-sc-num
- берёт: --bg-tertiary, --text-primary, --text-secondary

### styles/stats.css (129)
- Статистика: полоса срока, сетка карточек и сама коробка карточки. Что стоит внутри карточек — своими файлами.
- селекторы (22): .stats-toolbar, .stats-period-pill, .stats-refresh-btn, .stats-refresh-btn .material-symbols-outlined, .stats-refresh-btn.spinning .material-symbols-outlined, .stats-grid, .stats-card, .stats-card-title, .stats-col-6, .stats-col-12, .stats-loading, .stats-kpi-row, .stats-kpi-row .stats-card, .stats-kpi, .stats-kpi-num, .stats-kpi-num[data-tone='applied'], .stats-kpi-num[data-tone='progress'], .stats-kpi-num[data-tone='offer'], .stats-kpi-num[data-tone='decline'], .stats-kpi-label, .stats-kpi-delta, .stats-kpi-delta[data-tone='up']
- берёт: --accent, --bg-secondary, --border, --err, --ok, --status-applied, --status-offer, --text-secondary, --text-tertiary

### styles/status-color.css (62)
- Цвет статуса вакансии — один набор на всё окно. Красит три места: сегмент кольца, точку в списке рядом с ним и отрезок полосы воронки в карточке канала. Разойдись они, одна и та же ступень воронки была бы разного цвета на соседних экранах. Обводка и заливка названы вместе: у кольца цвет несёт stroke, у точки и отрезка — background. Сама точка объявлена здесь же: её ставят восемь компонентов на пяти экранах, а геометрия её лежала в файле экрана статистики — там её не нашёл бы никто, кроме автора. Незнакомый статус остаётся серым: цвет ему взять неоткуда, а пустое место читалось бы как пропущенная точка.
- селекторы (12): .status-dot, .donut-part[data-status='New'],
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
- берёт: --accent, --alert, --err, --fg-max, --info, --ok, --status-applied, --status-not-fit, --status-offer, --status-test, --text-tertiary, --warn

### styles/status-picker.css (63)
- Выбор статуса: что стоит внутри окошка под значком статуса. Оправа окошка — общая, в popover.css.
- селекторы (8): .status-picker, .status-options, .status-option, .status-option:hover, .status-option input, .popover-comment, .popover-actions, .popover-actions .btn
- берёт: --accent, --bg-tertiary, --selected-bg, --text-primary

### styles/status-pill.css (21)
- Плашка состояния в шапке секции: прижата к правому краю.
- селекторы (3): .status-pill, .status-pill[data-tone='ok'], .status-pill[data-tone='err']
- берёт: --danger, --err-fill-strong, --ok-fill, --ok-text

### styles/status-row.css (41)
- Строка состояния шага мастера: чем шаг занят и чем кончилось. Своим файлом, а не в оформлении мастера: строка — свой компонент, и стоит она на трёх шагах из четырёх. Стоит она там же, где работали: плашка поверх окна увела бы ответ туда, куда человек в этот миг не смотрит.
- селекторы (7): .status-row, .status-row .material-symbols-outlined, .status-row[data-tone='ok'], .status-row[data-tone='ok'] .material-symbols-outlined, .status-row[data-tone='err'], .status-row[data-tone='err'] .material-symbols-outlined, .status-row[data-tone='busy'] .material-symbols-outlined
- берёт: --accent, --bg-tertiary, --err, --ok, --text-primary

### styles/tabs.css (28)
- Верхние вкладки раздела: одна строка над содержимым экрана.
- селекторы (4): .top-tabs, .top-tabs .tab, .top-tabs .tab:hover, .top-tabs .tab.active
- берёт: --accent, --bg-secondary, --border, --text-primary, --text-secondary

### styles/tg-login.css (41)
- Окно входа в Telegram — своё, а не общее окно-вопрос. Отличия не в украшении: коробка у́же и без тени, потому что спрашивает одно короткое поле, а поле в ней темнее подложки — на общем цвете оно совпадает с коробкой, и человеку не видно, куда набирать код.
- селекторы (5): .tg-login, .modal-dialog.tg-login-box, .tg-login .modal-title, .tg-login .input, .tg-login .modal-actions
- берёт: --bg-tertiary

### styles/timeline.css (151)
- Лента жизни вакансии: точка, текст и время в три колонки.
- селекторы (26): .timeline, .tl-item, .tl-item .status-dot, .tl-item .status-dot[data-status=''], .tl-item .status-dot[data-status='Not Fit'], .tl-item.current .status-dot, .tl-item.current .status-dot[data-status='New'], .tl-item.current .status-dot[data-status='Applied'], .tl-item.current .status-dot[data-status='Answered'], .tl-item.current .status-dot[data-status='Test'], .tl-item.current .status-dot[data-status='Invitation'], .tl-item.current .status-dot[data-status='In Progress'], .tl-item.current .status-dot[data-status='Offer'], .tl-item.current .status-dot[data-status='Decline'], .tl-item.current .status-dot[data-status='Ghosting'], .tl-item.current .status-dot[data-status='Scam'], .tl-item.current .status-dot[data-status='Not Fit'], .tl-text, .tl-label, .tl-history-row, .tl-history-row .tl-label, .tl-event, .tl-note, .tl-note:focus, .tl-note::placeholder, .tl-when
- берёт: --bg-tertiary, --dot-outline, --status-not-fit-timeline, --text-primary, --text-secondary, --text-tertiary, --tl-halo-answered, --tl-halo-applied, --tl-halo-decline, --tl-halo-default, --tl-halo-ghosting, --tl-halo-in-progress, --tl-halo-invitation, --tl-halo-new, --tl-halo-not-fit, --tl-halo-offer, --tl-halo-scam, --tl-halo-test

### styles/toggle.css (64)
- Переключатель-пилюля: дорожка и шарик на ней. Двух размеров, и размер несущий: в анкете порогов он стоит один в колонке и взят в полный рост, а в строке списка контактов делит место с именем, счётом и значком отсева — там он вдвое меньше. Числа лежат переменными, чтобы шарик не пришлось пересчитывать на каждый размер руками.
- селекторы (7): .toggle, .toggle.compact, .toggle::after, .toggle:checked, .toggle:checked::after, .toggle:disabled, .toggle.locked:disabled
- объявляет: --toggle-gap, --toggle-h, --toggle-knob, --toggle-w
- берёт: --accent, --bg-primary, --bg-tertiary, --text-tertiary, --toggle-gap, --toggle-h, --toggle-knob, --toggle-w

### styles/trash.css (19)
- Корзина: кнопка, уносящая запись насовсем. Своим правилом, а не четырьмя одинаковыми у каждого списка: краснеют под курсором корзина строки отсева, места работы, категории навыков и самого навыка. Красное здесь до нажатия нарочно — серый ховер обычной кнопки-значка не отличал бы корзину от соседок, которые ничего не уносят. Само место, размер значка и отступы остаются за списком: у строки отсева кнопка полноразмерная, у навыка мельче, а у категории и места работы она вовсе не кнопка-значок.
- селекторы (1): .trash:hover,
.icon-btn.trash:hover
- берёт: --danger, --danger-tint

### styles/unnamed.css (16)
- Запись, у которой имени нет: её зовут словами, и слова эти набраны курсивом — так видно, что это не имя, а его отсутствие. Одним правилом на все четыре места, где безымянная запись показывается: шапка карточки контакта, строка списка, строка мини-списка в чужой карточке и подпись под именем человека, где так же зовут его компанию. Написанное порознь, оно расходится: пропавший в одном месте курсив читается как имя, а не как его отсутствие.
- селекторы (1): .cnt-det-name.muted,
.cnt-hr-name.muted,
.cnt-hr-sub .muted,
.hr-name.muted
- берёт: --text-tertiary

### styles/unread.css (103)
- Счёт непрочитанного: пилюля со значком письма и список под ней.
- селекторы (15): .badge-unread, .badge-unread .material-symbols-outlined, .badge-unread[data-has-unread='true'], .badge-unread:hover, .badge-unread[data-has-unread='true']:hover, .unread-popup-backdrop, .unread-popup, .unread-popup-empty, .unread-popup-list, .unread-popup-row, .unread-popup-row:last-child, .unread-popup-row:hover, .unread-popup-name, .unread-popup-sub, .unread-popup-count
- берёт: --accent, --accent-badge-hover, --selected-bg, --shadow-popup, --surface-raised, --surface-raised-hover, --text-primary, --text-tertiary

### styles/vacancies.css (166)
- Экран вакансий: список слева, подробности справа, строка в три этажа.
- селекторы (25): .vac-list-toolbar, .vac-list-toolbar .icon-btn, .vac-list-toolbar .icon-btn .material-symbols-outlined, .vac-list-toolbar .icon-btn:hover, .vac-sort-menu, .vac-sort-option, .vac-sort-option:hover, .vac-sort-option.active, .vac-list-empty, .vac-list-empty .material-symbols-outlined, .vac-detail-pane, .vac-detail-empty, .vac-row, .vac-row-head, .vac-title, .vac-meta, .vac-meta .v-co, .vac-meta .sep, .vac-meta .when, .vac-score, .vac-score[data-tone='warn'], .vac-score[data-tone='bad'], .vac-stack, .mini-chip, .mini-chip.more
- берёт: --accent, --accent-hover-soft, --accent-option-active, --bg-secondary, --bg-tertiary, --border, --err, --score-warn, --scrim, --text-primary, --text-secondary, --text-tertiary

### styles/vacancy-card.css (154)
- Карточка вакансии: шапка со статусом, чипы разбора, стек, текст и связи. Лента переходов — в timeline.css, выбор статуса — в status-picker.css, исходный текст — в raw-text.css, кружок с именами — в contact-block.css.
- селекторы (20): .det-head, .status-wrap, .det-title, .status-badge, .status-badge:hover, .status-label, .status-badge .material-symbols-outlined, .status-wrap.popover-open .status-badge .material-symbols-outlined, .det-info, .info-chip, .info-chip .material-symbols-outlined, .info-chip.linkable, .info-chip.linkable:hover, .info-chip.score, .info-chip.score[data-tone='warn'], .info-chip.score[data-tone='bad'], .det-stack, .stack-chip, .det-section p, .vac-contacts
- берёт: --accent, --bg-primary, --bg-secondary, --bg-tertiary, --border, --err, --score-warn, --text-primary, --text-secondary

### styles/vacancy-filters.css (133)
- Панель отбора вакансий: что стоит внутри окошка поверх списка. Оправа окошка — общая, в popover.css; группы условий — в filter-group.css.
- селекторы (20): .filter-wrap, .filter-btn.active, .filter-panel, .filter-head, .filter-head .material-symbols-outlined, .filter-title, .filter-meta, .filter-close, .filter-close:hover, .filter-close .material-symbols-outlined, .filter-panel .input, .filter-body .status-dot, .filter-body .choice:hover, .filter-pair, .filter-dates, .filter-dates .date-picker:last-child .date-panel, .filter-foot, .filter-foot .btn, .filter-foot .btn .material-symbols-outlined, .filter-foot-right
- берёт: --accent, --bg-tertiary, --scrim, --selected-bg, --surface-hover-firm, --text-primary, --text-secondary, --text-tertiary

### styles/wizard.css (269)
- Мастер первого запуска: полосы окна, обложка, финал и поджатия общих блоков под него. Полосы те же, что у самого приложения, и это нарочно: мастер — не отдельная программа, а первый разговор с этой. Что стоит внутри шага — карточки подсказок, инструкция, выбор файла, строка состояния — вынесено своими файлами: те же блоки встречаются и вне мастера.
- селекторы (38): .wiz-window, .wiz-steps, .wiz-steps.dimmed, .wiz-step, .wiz-step::before, .wiz-step:first-child::before, .wiz-step[data-mark='active']::before,
.wiz-step[data-mark='done']::before, .wiz-step-mark, .wiz-step[data-mark='active'] .wiz-step-mark, .wiz-step[data-mark='done'] .wiz-step-mark, .wiz-step-label, .wiz-step[data-mark='active'] .wiz-step-label, .wiz-step[data-mark='done'] .wiz-step-label, .wiz-body, .wiz-body > *:last-child, .wiz-head, .wiz-head .material-symbols-outlined, .wiz-head h1, .wiz-title, .wiz-text, .wiz-text strong, .wiz-foot, .wiz-foot-right, .wiz-done, .wiz-done .material-symbols-outlined, .wiz-done h2, .wiz-done .wiz-text, .wiz-subtitle, .wiz-subtitle strong, .wiz-welcome, .wiz-window .input, .wiz-window .btn, .wiz-window .btn .material-symbols-outlined, .wiz-body > .info-card,
.wiz-body > .warning-card, .wiz-fields, .wiz-modes, .wiz-window .cdd-btn, .wiz-fields .help
- берёт: --accent, --accent-chip-selected, --bg-primary, --bg-secondary, --bg-tertiary, --border, --text-primary, --text-secondary, --text-tertiary

## tests — 70 файлов

### tests/alive.test.js (79)
- —

### tests/ask_dialog_live.test.js (55)
- * Окно с записанным за ним следом нажатий.

### tests/attempts.test.js (32)
- —

### tests/autosave.test.js (139)
- —

### tests/autosize.test.js (85)
- * Поле, помнящее всё, что ему ставили в высоту. * * Измеренная высота отвечает по последнему поставленному: настоящее поле * меряет содержимое ровно так — сжатое до `auto` показывает свой текст, а * растянутое прежним значением показывает это самое прежнее.

### tests/avatar.test.js (27)
- —

### tests/blacklist.test.js (201)
- —

### tests/blacklist_menu_item.test.js (114)
- * Кому эти слова положены: сам пункт, окошко ручного занесения и кнопка на * вкладке отсева. Всем прочим — нет: там это была бы четвёртая копия.

### tests/blacklist_menu_item_live.test.js (67)
- * Пункт с записанным за ним следом нажатий.

### tests/bottom_bar_live.test.js (109)
- —

### tests/bridge.test.js (161)
- —

### tests/bridge_stub.js (41)
- * Мост, отвечающий заготовленным по очереди; зовы копятся в `asked`.
- отдаёт: replying, rereading, tracing

### tests/calendar.test.js (60)
- —

### tests/card_block.test.js (94)
- * Карточка, записывающая всё, что с ней сделали.

### tests/card_finish.test.js (71)
- * Панель, записывающая всё, что с ней сделали, — в том порядке, в каком делали.

### tests/card_links.test.js (37)
- —

### tests/card_notes.test.js (53)
- * Карточка с заметкой, записывающая всё, что с ней сделали.

### tests/card_read.test.js (87)
- —

### tests/card_save.test.js (50)
- * Карточка, записывающая всё, что с ней сделали.

### tests/channel_card_live.test.js (78)
- * Сколько раз спросили названный слот.

### tests/channel_row_live.test.js (99)
- * Строка канала с записанными нажатиями.

### tests/channels.test.js (186)
- —

### tests/channels_list_live.test.js (67)
- —

### tests/chat.test.js (157)
- —

### tests/chosen.test.js (40)
- —

### tests/companies.test.js (141)
- —

### tests/confirm_tone_live.test.js (75)
- * Карточка с привязанным HR: без него пункт отправки заперт.

### tests/dates.test.js (111)
- —

### tests/events.test.js (205)
- * Мост, отвечающий заготовленным, а на исходе — закрытой очередью.

### tests/experience.test.js (118)
- —

### tests/flash.test.js (34)
- —

### tests/footer.test.js (152)
- * Нажатие мышью: место на дорожке шириной 300 точек.

### tests/fresh.test.js (71)
- * Ответ, который держат в руке: отдают его, когда скажут.

### tests/keys.test.js (97)
- —

### tests/live_props.svelte.js (21)
- * Заводит набор свойств и способ поменять одно из них. * * Отдаёт вид с геттером на каждое имя: читающий трогает ровно то свойство, * которое назвал, а не весь набор.
- отдаёт: livingProps

### tests/logs.test.js (152)
- —

### tests/markup.js (81)
- * Файлы разметки вместе с содержимым.
- отдаёт: markup, placed, placementsIn

### tests/markup.test.js (69)
- —

### tests/new_vacancy_fields_live.test.js (84)
- —

### tests/notes_field.test.js (66)
- * Файлы разметки, ставящие поле заметки, вместе с их содержимым.

### tests/notes_field_delay_live.test.js (51)
- —

### tests/notes_field_live.test.js (62)
- * Поле заметки с записанными за ним отправками.

### tests/one_write.test.js (139)
- * Запись, которая отвечает не сразу: ответ отдаёт вызывающий.

### tests/open_mark.test.js (36)
- —

### tests/outside.test.js (122)
- * Узел, считающий своими только перечисленные цели.

### tests/paged_list.test.js (179)
- * Прокрутка, доехавшая до низа списка.

### tests/paging.test.js (61)
- —

### tests/people.test.js (208)
- —

### tests/people_list_live.test.js (74)
- * Вкладка «HR» с мостом, отвечающим не раньше, чем ему позволят.

### tests/person_chat_live.test.js (70)
- * Переписка с записанными за ней просьбами к мосту.

### tests/picker.test.js (134)
- —

### tests/profile.test.js (115)
- —

### tests/profile_experience_live.test.js (72)
- * Вкладка с записанными за ней посылками на мост.

### tests/provider.test.js (101)
- * Отказ моста в том виде, в каком его поднимает обёртка зова.

### tests/search.test.js (49)
- —

### tests/settings.test.js (277)
- —

### tests/settled.js (21)
- * Дождаться, пока осядут ответы моста и отрисовка.
- отдаёт: settled

### tests/skills.test.js (130)
- —

### tests/stats.test.js (273)
- —

### tests/suggest_input_live.test.js (92)
- —

### tests/vacancies.test.js (285)
- —

### tests/vacancies_screen_new_live.test.js (301)
- * Мост, отвечающий тем же, чем отвечает настоящий. * * Заведение чужой карточки отказывает: так ведёт себя настоящий, когда имя * занято или связь оборвалась, — и это единственный способ увидеть, что * остаётся в черновике после неудачи.

### tests/vacancy_actions.test.js (127)
- —

### tests/vacancy_card.test.js (287)
- —

### tests/vacancy_card_live.test.js (80)
- —

### tests/vacancy_detail.js (37)
- * Карточка вакансии от моста; названное в `extra` перебивает заготовку.
- отдаёт: vacancyDetail

### tests/vacancy_filter.test.js (241)
- —

### tests/vacancy_timeline_live.test.js (43)
- —

### tests/wizard.test.js (194)
- —

### tests/wizard_cv_live.test.js (108)
- * Шаг с подставным мостом: след зовов и способ доставить весть об исходе. * * `during` доставляет весть посреди самого зова разбора — так приходят * мгновенные отказы: файл пропал, формат не читается, текста в файле нет.

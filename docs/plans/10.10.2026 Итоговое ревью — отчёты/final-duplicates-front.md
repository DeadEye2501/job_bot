# Итоговое ревью: повторы во фронте по карте

Карта `docs/maps/front-map.md` (1807 строк) прочитана целиком, в три прохода:
1. сплошное чтение всех слоёв: app, components, state, styles, tests;
2. стили и компоненты ещё раз — сверка одинаковых наборов объявлений, наведений,
   рамок окошек и подписей;
3. состояние и тестовые помощники — сверка таблиц, фраз, подставных мостов и
   поиска кнопок по подписи.

Файла `docs/not-duplicates.md` нет. Каждый пункт ниже подтверждён чтением обоих
мест в коде. Дифф не читался.

## Strengths

- Свежий код по большей части опирается на готовое, а не пишет своё.
  `ScreeningDialog` берёт ленту и пузыри переписки (`chat.css`).
  `ApplyWaysDialog` берёт строку подборщика и `ModalFoot`. `MailSection` стоит на
  `SettingsSection` и `SecretInput`. `MailPasswordHelp` стоит на `.help`.
  `RUNNING` объявлен один раз (`state/round.svelte.js:13`), его читают четыре
  места. `pasteLock` построен на `typed`. `humanText` лежит рядом с прочими
  подписями хода.
- Общие механизмы источников вынесены: `sourceList`, `sourceCard`,
  `sourceToggle`, `SourceRow` и `RowMarks`. Строки канала и агрегатора стали
  тонкими обёртками.
- Опора для чисел и дат одна: `fillPercent`, `padded`, `plural`, `matching`.
  Склеек `levelPercent`/`scorePercent` и `pickNames`/`groupsMatching` поверх неё
  достаточно, своих копий нет.
- Общие файлы оформления написаны со своим доводом: `row-hover`, `caption`,
  `clipped-line`, `accent-fill`, `accent-outline`, `trash`, `count-pill`,
  `card-section`, `master-detail`, `scroll-body`, `status-color`.
- Тестовые помощники вынесены: `bridge_stub`, `settled`, `markup`,
  `live_props`, `vacancy_detail`. Новый `vacancy_card_mount.js` сразу собрал
  монтаж карточки для трёх живых проверок.

## Issues

### Critical (Must Fix)

Нет.

### Important (Should Fix)

**1. Сброс шрифта и прижим вправо у плашки состояния повторяют новую обёртку
шапки секции.** Это свежий код.

- `client/web/styles/status-pill.css:3-11`, у `.status-pill`: `margin-left: auto;
  font-weight: 400; letter-spacing: 0; text-transform: none;`.
- `client/web/styles/settings-section.css:38-46`, у `.settings-section-side`
  (добавлена в 251040f): тот же набор, `margin-left: auto; text-transform: none;
  letter-spacing: 0; font-weight: 400;`.
- `StatusPill` ставит только `SettingsSection.svelte:19`, и только внутри
  `.settings-section-side`. Поэтому четыре объявления пилюли — копия обёртки, а
  сами по себе ничего не делают. Тронь кто-нибудь сброс у обёртки — у пилюли
  останется прежний.
- Что оставить: `.settings-section-side`. Из `.status-pill` убрать эти четыре
  строки, оставить кегль, отступ, скругление и тона. Комментарий «прижата к
  правому краю» в `status-pill.css:1` после этого переехать к обёртке.

**2. Наведение на пункт во всплывающем перечне написано семь раз, и две копии
уже разошлись. Меню порядка к тому же рисует свою оправу окошка.**

- Одним цветом, `background: var(--selected-bg)`, пункт под курсором отвечает в
  пяти местах:
  - `styles/menu.css:25` — `.menu-item:hover`;
  - `styles/dropdown.css:78` — `.cdd-option:hover`;
  - `styles/blacklist-dialog.css:110` — `.bl-combobox-option:hover`;
  - `styles/status-picker.css:31` — `.status-option:hover`;
  - `styles/skill-picker.css:73` — `.skill-picker-item:hover`.
- Разошлись две копии:
  - `styles/vacancies.css:48` — `.vac-sort-option:hover` даёт
    `--accent-hover-soft`;
  - `styles/unread.css:80` — `.unread-popup-row:hover` даёт `--surface-raised`.
- Смысл везде один: «пункт, по которому попадёт нажатие». Это ровно тот
  случай, что `row-hover.css` уже свёл для строк перечней, только для окошек.
- Оправа меню порядка: `styles/vacancies.css:26-37`, `.vac-sort-menu`.
  - Своя подложка, рамка, скругление `5px` и тень `0 8px 22px var(--scrim)`.
  - Это вместо `.pop`/`.pop-frame` из `styles/popover.css:15-21`, где скругление
    `6px` и тень `var(--shadow-popup)`.
  - `popover.css` прямо называет себя оправой всех всплывающих панелей, а меню
    порядка в него не входит.
  - Тень `0 8px 22px var(--scrim)` к тому же записана второй раз у соседней
    панели отбора: `styles/vacancy-filters.css:29`, она стоит поверх `.pop`.
- Что оставить:
  - одно правило наведения пункта всплывающего перечня, своим файлом рядом с
    `row-hover.css`, со значением `--selected-bg` (так отвечает большинство). В
    него сгруппировать все семь селекторов, `vac-sort-option` и
    `unread-popup-row` перевести на общее;
  - у `.vac-sort-menu` — разметкой класс `pop`. Тень обеих панелей полосы
    вакансий держать одним правилом, сгруппировав `.vac-sort-menu` с
    `.filter-panel`.

**3. Подпись капителью повторена мимо `caption.css`, и одна копия уже
разошлась.**

- `styles/caption.css:14-22`: `color: var(--text-tertiary); letter-spacing:
  0.4px; text-transform: uppercase`. Файл заявлен «одним правилом на все
  подписи» и предупреждает: «у одной подписи пропадает разрядка».
- `styles/filter-group.css:12-18`, `.filter-label`: та же тройка, но разрядка
  `0.3px` — разошлась.
- `styles/stats-channels.css:56-64`, `.stats-ch-grid .stats-ch-th`: та же
  тройка дословно (`0.4px`). Это шапка таблицы — то же, что `.bl-row.head`,
  которую `caption.css` уже держит.
- `styles/stats-channels.css:32-36`, `.stats-ch-grid .stats-ch-group`: та же
  тройка с разрядкой `0.6px`. Цвет потом перекрашивается по группе
  (`:50-52`).
- Что оставить: `caption.css`. Дописать в его селектор `.filter-label`,
  `.stats-ch-th` и `.stats-ch-group`. У каждого оставить кегль и отступы, у
  групп — их цвет, который перебивает общий.

**4. Строка файла резюме написана дважды — в анкете и в мастере. Копии
расходятся правилом рамки и словами.**

- Анкета: `components/CvFileRow.svelte:10-24` и `styles/cv-file.css:3-12`
  (`.pdf-row`). Рамка `1px dashed` всегда, в том числе при выбранном файле.
  Значок 28px, подложка `--bg-secondary`. Пустое состояние —
  `state/profile.js:69`: «Файл не выбран».
- Мастер: `app/WizardCv.svelte:145-157` (разметка прямо в экране) и
  `styles/file-pick.css:7-18` (`.file-pick`). Рамка пунктиром до выбора и
  сплошная после. Довод в самом файле: «пустая строка со сплошной рамкой…» и
  «сплошная рамка после — что файл уже взят». Значок 22px, подложка
  `--bg-tertiary`. Пустое состояние — «Файл ещё не выбран».
- Предмет один: значок, имя с размером (оба зовут `fileSize`) и «Заменить».
  Правило рамки при этом прямо противоположное: анкета показывает взятый файл
  пунктиром, то есть тем, чем мастер обозначает «сюда кладут».
- Что оставить: `CvFileRow`. Строку мастера поставить им. Своё у мастера —
  кнопка «Выбрать» без файла и отсутствие «Открыть» — передать фрагментом
  действий. Подписи брать из `cvNote`. Правило рамки взять из `file-pick.css`,
  а `cv-file.css` свести к нему.

### Minor (Nice to Have)

**5. Вкладки «Каналы» и «Агрегаторы» — одна разметка с двумя наборами слов.**
Это свежий код.

- `app/ChannelsList.svelte` и `app/AggregatorsList.svelte`. Свойства
  одинаковые: `ask, say, lockedTip, events, open, onopened, onvacancy`. Каркас
  один в один: `ContactsPanes`, поиск, `AddButton`, общий `RowToggle`, перебор
  строк, карточка справа, `AddressDialog` с семью одинаковыми привязками
  `newX.*`.
- Механизмы уже общие: `sourceList`, `contactAdding`, `watchContacts`.
  Разметка осталась в двух копиях.
- Разница — в словах, в методах моста и в двух подписках у агрегаторов
  (`round.onFinish`, `missed`). Второй экземпляр уже расходится: у каналов есть
  ветка «Каналов пока нет», у агрегаторов её нет. Это объяснимо: «Поиск по
  сети» стоит в списке всегда.
- Что оставить: одну вкладку источников, которой строку и карточку передают
  фрагментами, а слова, чтение и заведение — доводами. Обе нынешние вкладки
  станут её постановками.

**6. Наведение на строку подборщика в окне «Куда откликнуться» ответвлено от
общего.** Это свежий код.

- `styles/apply-ways.css:12-15`: `.picker-row.way-row:hover` — серая подложка и
  светлая рамка.
- `styles/row-hover.css:22`: та же `.picker-row` в окне выбора (`PickerDialog`)
  под курсором отвечает лаймовым `--accent-row-hover`.
- Довод ответвления («лайм здесь значит выбранную») верен и для окна выбора:
  там выбранная строка залита тем же `--selected-bg`
  (`picker.css:49-52`). Выходит, одна строка в двух окнах отвечает на курсор
  по-разному без разницы в смысле.
- Что оставить: одно наведение у `.picker-row`. Если серое правильнее — перенести
  его в `picker.css`, а строку подборщика убрать из `row-hover.css`. Это меняет
  вид окна выбора, поэтому решать человеку.

**7. Надпись «здесь пусто» трижды написана мимо `.empty-note`.**

- `styles/empty-note.css:4-9` объявлен «одной на все экраны». Его носят
  `cnt-list-empty`, `picker-empty`, `unread-popup-empty` и другие.
- Своими блоками (приглушённый цвет, по центру, кегль и отступ) повторяют то же:
  - `styles/chat.css:46-51` — `.cnt-chat-empty`;
  - `styles/blacklist-dialog.css:126-131` — `.bl-combobox-empty`;
  - `styles/channel-stats.css:73-78` — `.ch-stats-empty`.
- Что оставить: `.empty-note`. Этим трём разметкой добавить класс `empty-note`,
  своим оставить только отступ и кегль — так уже сделаны `picker-empty` и
  `unread-popup-empty`.

**8. Чип сведений в шапке карточки написан у вакансии и у контакта
по-отдельности.**

- `styles/vacancy-card.css:84-97` — `.info-chip`.
- `styles/contact-card.css:84-92,106-108` — `.cnt-det-meta-chip`. Кегль `0.72rem`
  ему задаёт ряд в `:77`.
- Одинаковы: `inline-flex`, выравнивание, `gap: 4px`, подложка
  `--bg-tertiary`, цвет `--text-secondary`, значок 12px. Уже разъехались:
  отступ `2px 8px` против `1px 7px`, скругление `10px` против `9px`.
- Что оставить: одно правило чипа сведений своим файлом. В него сгруппировать
  оба селектора. Тона (`score`, `unread`, `blacklist`, `linkable`) оставить при
  своих.

**9. Пилюля уровня журнала повторяет форму пилюли выбора.**

- `styles/pill.css:7-18`: `.pill` — рамка `1px var(--border)`, скругление
  `12px`, подложка `--bg-secondary`; под курсором рамка `--accent`.
- `styles/log-level-pill.css:7-29`: `.logs-level-pill` — те же четыре
  объявления и тот же отклик на курсор.
- Своё у пилюли журнала (тон зажатой, моноширинный шрифт, счёт) объяснено.
  Форма и наведение — нет.
- Что оставить: `.pill`. Пилюле журнала добавить разметкой класс `pill`, у
  `.logs-level-pill` оставить только своё.

**10. «Убрать строку из списка» у достижений сделано своим наведением, а не
крестиком.**

- `styles/remove-cross.css`: серый крестик, под курсором красный, без
  подложки. Файл так и называет случай: «лёгкое „убрать из списка“».
- `components/BulletList.svelte:31` и `styles/bullet-list.css:78-82`: кнопка-значок
  `close`, которой наведение перебивают на `color: var(--danger); background:
  transparent` — тот же смысл и тот же вид, своим правилом.
- Что оставить: `.remove-cross`. Своим у списка достижений остаётся появление
  по наведению на строку (`opacity`).

**11. Ник с собакой собирается мимо `state/telegram.js`.**

- `state/telegram.js:13` объявлен домом написания ника («второе его написание
  разошлось бы с первым молча»). При этом ``x ? `@${x}` : …`` собирается
  руками в местах, где у каждого своё запасное слово:
  - `state/channels.js:17,19`;
  - `state/people.js:32,138`;
  - `state/settings.js:296`;
  - `state/vacancy_actions.js:107`;
  - `state/vacancy_card.js:98`;
  - `state/picker.js:48`;
  - `app/PersonCard.svelte:189`;
  - `components/CardHandle.svelte:19`;
  - `components/MiniPeople.svelte:31`.
- Что оставить: `telegram.js`. Завести в нём «ник с собакой или пусто», а запасные
  слова оставить у зовущих.

**12. Нажатие кнопки по подписи в тестах.**

- `tests/vacancy_card_mount.js:56-61` — `press(label)`, это свежий код.
  Помощник общий, но лежит в файле карточки вакансии.
- Тот же поиск вписан дословно в `tests/tg_login_dialog_live.test.js:47`.
- Вариант с точным совпадением повторён в
  `tests/vacancies_screen_new_live.test.js` восемь раз: «Создать» —
  `:167,191,223,249,268`, «Текст» — `:207,263,313`.
- `tests/vacancy_screening_live.test.js:44` ищет пункт меню по подписи тем же
  способом.
- Что оставить: `press` — перенести в общий помощник рядом с `settled.js`, дать
  ему выбор между вхождением и точным совпадением, перевести на него
  перечисленные места.

**13. Ответ, отпускаемый по команде, в тестах объявлен дважды под одним
именем.**

- `tests/fresh.test.js:8-12` — `held(value)`.
- `tests/provider_form.test.js:31-37` — `held()`.
- Тот же приём вписан ещё и прямо в проверки:
  - `contact_adding.test.js:98-101`;
  - `source_vacancies.test.js:97-100`;
  - `paged_list.test.js:153-154`;
  - `people_list_live.test.js:25-28`.
- Что оставить: один `held` в общем помощнике тестов, например в
  `bridge_stub.js`, где уже лежат подставные ответы.

**14. «Мост, записывающий зовы и отвечающий по методу» написан в каждой живой
проверке заново.**

- Дом подставного моста — `tests/bridge_stub.js`, где `replying` отвечает по
  очереди.
- Отвечающий по имени метода объявлен отдельно в
  `tests/provider_form.test.js:15-23`.
- Ещё по разу — обёрткой `asked.push` вокруг своего ответа:
  - `tests/vacancy_card_mount.js:21-24` (свежий код);
  - `settings_screen_live.test.js:43-48`;
  - `person_chat_live.test.js:38-43`;
  - `people_list_live.test.js:29-36`;
  - `bottom_bar_live.test.js:32-38`.
- Форма следа у них при этом разная: где пара, где объект.
- Что оставить: в `bridge_stub.js` — помощник «отвечает функцией
  `answer(method, payload)`, зовы копятся в `asked`». На него перевести
  перечисленные места, `provider_form` — тоже, передав таблицу ответов функцией.

## Declined to judge

- `mailPill` / `sessionPill` / `probePill` (`state/settings.js`): один глагол над
  разными предметами — разные условия и слова.
- `actionBlocks` (`vacancy_actions.js:23`) / `actionBlock` (`aggregators.js:52`) /
  `pollBlock` (`channels.js:44`): порядок причин у них разный и объяснён рядом;
  предмет разный.
- «В чёрном списке — снимите запись, чтобы …» (`sources.js:17`,
  `aggregators.js:54`): обе фразы — дословные отказы моста на разные действия.
- `convNote` (`stats.js:174`) / `share` (`sources.js:81`): доли разных полей
  моста (`conv_*` и `*_percent`), разная точность, разные экраны.
- `channelRows` / `SOURCE_ROW` (`stats.js`) и `sourceStats` (`sources.js`):
  таблица воронки и плитки карточки — разные выдачи.
- `STATUS_CHOICES` (`statuses.js`) и `STATUS_ORDER` (`stats.js`): первая построена
  из второй.
- `named` (`people.js:59`) и `named` (`profile.js:92`): общее слово в имени,
  разные дела.
- `UNNAMED` в `people.js:12` и в `unnamed.js:17`: разные слова, разница объяснена
  в обоих файлах.
- `shortDate` / `showDate` / `showStamp` / `chatTime` / `logTime` / `ago` /
  `shortAgo` / `duration`: разные виды времени, общая часть (`padded`,
  `agoHead`) уже вынесена.
- `fillPercent` / `levelPercent` / `scorePercent`: склейки над одним
  объявлением.
- `contactHref` / `siteHref`: первая зовёт вторую.
- `CompanyRow` / `PersonRow` / `SourceRow`: кнопка против строки с ролью кнопки
  (внутри переключатель), разные хвосты; общее (`RowMarks`, `Avatar`) вынесено.
- `ChannelCard` / `AggregatorCard`: общие механизмы вынесены, остаток сильно
  разный (вход, запоры агента, подтверждение удаления).
- `ConfirmDialog` / `AskDialog`, `TgLoginDialog` / `AddressDialog`: разная
  раскладка, своё объяснено (`modal.css`, `tg-login.css`).
- `ApplyWaysDialog` / `PickerDialog`: двухшаговый выбор похож, но подборщик несёт
  поиск, чтение и заведение — тащить его ради пяти строк незачем.
- `ScreeningDialog` / `RawTextDialog` / `MailPasswordHelp`: разные тела на общей
  раме окна.
- `NotesField` / `DelayedTextarea`: разница объяснена в шапке
  `DelayedTextarea`.
- `CardHandle` / `Handle`: шапка карточки против строки списка, разница
  объяснена.
- `BlacklistChip` / `BlacklistMark`: шапка против хвоста строки.
- Три одинаковых шага в `MailPasswordHelp.svelte` («Впишите название…»,
  «Скопируйте его сразу…»): это текст инструкции по разным почтам, а не
  объявление.
- `.filter-close` / `.modal-close`, `.filter-head` / `.modal-head`: панель уже
  носит общие классы, отличия объяснены.
- `.settings-page .btn.danger` / `.btn.danger`: контурный вариант объяснён.
- `.cnt-add-btn` / `.bl-add-btn`: исключение объяснено в `accent-outline.css`.
- `.help .help-link:hover` / `.info-chip.linkable:hover`: связь названа
  комментарием, объявление одно.
- `.chip:hover .chip-x`: крестик внутри чипа краснеет по наведению на чип — своё
  условие.
- `.human-plate` / `.status-pill` / `.status-row`: смысловые тона на разных
  блоках.
- Цвета наведения строк вне `row-hover.css` (`.vac-mini-row`, `.hr-mini-row`,
  `.stats-sc-item`): у мини-списков свой довод в `mini-list.css`, у счётчиков
  статусов — ячейка, а не строка перечня.
- `source_card.test.js:19` `settle` / `settled.js`: один оборот против восьми,
  разное ожидание.
- `afterEach` с разборкой карточки в трёх живых проверках карточки: три строки,
  выносить нечего.
- Тестовые «карточки, записывающие всё» в `card_block`, `card_save`,
  `card_notes`: разные предметы поверх общего `tracing`/`rereading`.

## Assessment

**Ready to merge?** With fixes

**Reasoning:** Критичного нет. Свежий код опирается на готовое, и только пункт 1
(сброс у плашки состояния повторяет новую `.settings-section-side`) родился в
этом этапе. Пункты 2-4 — старые пары, которые уже разошлись: наведение в
окошках, подпись капителью, строка файла резюме. Каждую из них общий файл или
компонент рядом заявляет своей, и чинить их стоит прежде, чем они разойдутся
дальше.

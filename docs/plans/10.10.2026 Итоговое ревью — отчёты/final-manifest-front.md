# Итоговое ревью: манифест во фронте (`client/web`), 174c0ca..251040f

Правила 2, 6, 7, 10, 11, 13, 14, 16 в фронтовом чтении. Прочитаны: MANIFEST.md, раздел
SKILL.md «Восемь правил…», `.claude/clean.json`, полный дифф `components/`, `app/`,
`state/`, `styles/`, `tests/`, `main.js`; карта фронта сверена по именам новых модулей.

## Strengths

- **Слои соблюдены по направлению (п. 10).** Ни один компонент не импортирует
  `*.svelte.js` и `$api`: общий учёт прогона (`state/round.svelte.js`) читают только
  сборки (`BottomBar`, `AggregatorCard`, `AggregatorsList`, `VacancyCard`,
  `VacanciesScreen`), а подписывает его один раз оболочка (`Shell.svelte` → `hearRound`).
  Компоненты получают только пропсы и чистые функции из `state/*.js`.
- **Повторы вынесены по ответственности, а не по счёту потребителей (п. 7).**
  `SourceRow` (строка канала и агрегатора; `ChannelRow` и `AggregatorRow` стали тонкими
  обёртками рода), `RowMarks` (хвост строки у компании и источника), `SourceStats`
  (числа и воронка из `ChannelCard` переехали без правок), `AddButton`, `AddressDialog`
  (канал, агрегатор, контакт вакансии; слова уехали в `NEW_CARD`).
- **Логика ушла из сборок в `state` (п. 6, 10).** `provider_form.svelte.js` свёл
  одинаковую логику полей поставщика из `SettingsScreen` и `WizardLlm`; `source_list`,
  `source_card`, `source_vacancies` свели вкладки и карточки источников; `contact_adding`
  забрал заведение канала, которое раньше было написано в `ChannelsList` руками;
  `siteHref` переехал из `companies.js` в нейтральный `site.js` вместе со своими тестами.
- **У каждого нового блока свой файл оформления (п. 2, «стиль блока своим файлом»):**
  `add-link.css`, `remove-cross.css`, `input-pair.css`, `human-plate.css`,
  `login-mark.css`, `apply-ways.css`, `vacancy-contacts.css`. Старые копии
  (`.lang-remove`, `.list-add:hover`, сессия в `settings.css`) удалены, а не оставлены рядом.
- **Комментарии почти везде объясняют решение, а не пересказывают код (п. 11).** Например,
  `round.svelte.js` про синхронный `onStart`, `TgLoginDialog` про то, что blur срабатывает
  раньше «Войти», `ApplyWaysDialog` про двухшаговый выбор, `toggle.css` про `muted` без прозрачности.
- **Тесты в основном проверяют поведение через живой монтаж (п. 13):** окно выбора
  способа отклика, плашка ожидания человека, скрининг, гонки «выбрали другую вакансию,
  пока ехал ответ», почта в настройках, переход по строкам таблицы источников.

## Issues

### Critical (Must Fix)

Нет.

### Important (Should Fix)

1. **П. 6 / 2 / 11: `state/contacts_watch.js:1-11, 26-45`, у модуля две ответственности, а его шапка неверна.**
   - *Что не так.* `watchSourceCard` (заход на карточку источника, весть
     `vacancies_list_changed`, `forget`/`read`) дописан в модуль захода на вкладку
     контактов (весть `contacts_lists_changed`, `list.again`). Шапка теперь описывает модуль
     с «и» («Заход на вкладку контактов и на карточку источника»). Обоснование ниже по-прежнему
     говорит «вкладок таких две — люди и компании» и «бот заводит людей и компании сам».
     На деле `watchContacts` зовут четыре вкладки (`ChannelsList`, `AggregatorsList`,
     `CompaniesList`, `PeopleList`), а к `watchSourceCard` эти слова не относятся вовсе.
     Потребитель у `watchSourceCard` один: `state/source_card.svelte.js:57`.
   - *Почему важно.* Тот, кто ищет по карте «дело», найдёт заход на карточку там, где по
     описанию лежат только списки. А устаревшее «две вкладки» прямо вводит в заблуждение.
   - *Как чинить.* Перенести `watchSourceCard` в `source_card.svelte.js`, где его единственный
     потребитель и уже есть `forget` и `reread`. Вернуть шапке `contacts_watch.js` одну
     ответственность и переписать довод без перечня вкладок.

### Minor (Nice to Have)

2. **П. 2 (место оформления): `styles/contact-card.css:64-66`.** `.vac-contact-link:hover`
   (блок контактов вакансии) лежит в файле шапки карточки контакта. Комментарий в
   `vacancy-contacts.css:23` отсылает туда. Стиль чужого блока живёт не в своём файле. Так
   обошли сторожа дублей, но правило «стиль блока своим файлом» нарушено. Как чинить:
   общую подсветку ссылки вынести отдельным классом (например, в `add-link.css`
   соседним правилом или своим маленьким файлом) и навесить его на обе кнопки.
3. **П. 2: `styles/form-grid.css:32-42`.** `.name-grid` (строка имени анкеты: пары
   полей и плитки пола) описан в файле общей сетки формы. Это свой блок, и ему нужен свой файл
   (например, `name-grid.css`) или место рядом с `input-pair.css`.
4. **П. 2: `state/aggregators.js:14`, `state/vacancies.js:9`, `state/vacancy_actions.js:7`.**
   Чистые модули импортируют `RUNNING` из `round.svelte.js`, то есть из модуля с общим
   изменяемым состоянием на уровне модуля. Направление слоя не нарушено (state → state),
   но чистая логика теперь тянет за собой синглтон и руны ради одной строки текста. Как чинить:
   держать `RUNNING` в чистом файле (например, `progress.js` или `sources.js`), а
   `round.svelte.js` пусть реэкспортирует его или берёт оттуда.
5. **П. 10 (компонент ничего не вычисляет): `components/MailSection.svelte:28, 43`.**
   В обработчиках компонента стоят решения: «слать пароль, только если сменился»
   (`password !== (mail.password ?? '') && onsave(...)`) и разбор порта
   (`Number.parseInt(...) || null`). Как чинить: отдавать набранное как есть, а сравнение
   и приведение перенести в `saveMail` сборки или в чистую функцию `state/settings.js`.
6. **П. 6 (сборка только собирает): `app/SettingsScreen.svelte:124-133`.** `saveMail`
   сам собирает полезную нагрузку моста, подставляя умолчания (`?? ''`, `?? null`).
   Это приведение формы к виду моста, и ему место рядом с `mailPill`/`mailNeedsServer`
   (`state/settings.js`), как у анкеты (`profileSheet`).
7. **П. 6: `app/AggregatorCard.svelte:110-124`.** Кнопка входа рядом с именем свёрстана
   прямо в сборке, со своим тернарием подписи в разметке. Шапки карточек в `app/` и до
   этого собирались разметкой (так написаны `ChannelCard` и `CompanyCard`), поэтому это
   продолжение принятого порядка, а не новый прецедент. Но кнопка-отметка входа —
   самостоятельный показ («выполнен ли вход» и «войти заново») со своим оформлением
   `login-mark.css`, и как компонент `LoginMark` она читалась бы честнее.
8. **П. 11 (устаревшие счёты в комментариях).**
   - `styles/palette.css:170`: «Текст на тихой заливке свой у трёх видов». После
     добавления агрегатора своих `--kind-*-fg` четыре (keyword, company, channel,
     aggregator). Это ровно та порча, из-за которой счёт в комментариях запрещён.
   - `state/vacancy_card.js:494-495` (в диффе): «родов больше десятка». В `EVENT_TEXT`
     десять записей, так что утверждение неточно. Довод «таблица не удлиняет функцию»
     держится и без числа.
   - `state/stats.js:134`: «строка, собравшая всё, что пришло не из канала». Теперь это
     строка рода `none`, то есть ни из канала, ни с агрегатора. Документация `channelRows`
     уже говорит «по источникам», а сама функция и константа `NO_CHANNEL` названы по-старому.
   - `components/SettingsSection.svelte:4-5`: «ради двух кнопок». Довод не зависит от числа.
9. **П. 13/14: `tests/settings_screen_live.test.js:1629-1634`, «строки о сеансе Telegram
   под полями нет».** Тест проверяет отсутствие фразы «Сессии нет», а производившая её
   функция `sessionText` удалена в этом же диапазоне. Нет строки кода, поломка которой
   сделала бы тест красным: покраснеет он, только если кто-то дословно вернёт эту фразу. Это
   описание удаления, а не сторож. Как чинить: удалить тест. Наблюдаемое следствие («о сеансе
   говорит плашка в шапке») уже покрыто соседним тестом про кнопки в шапке и `sessionPill`.
10. **П. 13: `tests/sources.test.js:2173-2186` (в диффе).** Имена «нажатием выключает
    обход» / «нажатием возвращает обход» обещают поведение, а тело сравнивает
    возвращённый объект `{checked, title}` с литералом. Нажатия в тесте нет. Как чинить:
    переименовать по тому, что тест наблюдает («подпись называет, что сделает нажатие»), или
    проверить нажатие на живой вкладке (`setAll` с нужным `is_active`).
11. **П. 13 / 2: `tests/confirm_tone_live.test.js`.** Проп `tone` удалён, кнопка
    подтверждения всегда `danger`. В файле остался один тест, который проверяет литерал
    класса, а имя файла говорит о «тоне», которого больше нет. Как чинить: переименовать по
    тому, что он сторожит (подтверждение удаления), или влить в `vacancy_card_live.test.js`.

## П. 14: какая строка делает красным каждый новый тест

Сгруппировано по файлам; внутри файла каждый тест сторожит названную строку.

- `aggregators.test.js`: `aggregatorWhere` (тернарий `is_web_search`), `aggregatorLastRun`
  (ветка `last_run_at`), `aggregatorToggle` (`open: is_logged_in && !is_blacklisted`,
  выбор `lockTitle`), `actionBlock` (порядок `blocked` → `running` → `lock || lockedTip`).
- `blacklist.test.js`: `kindOptions` (подпись со счётом по `one.key`), `kindPicked` (`indexOf`),
  `kindIndex` (`findIndex`).
- `bottom_bar_live.test.js`: `{#if round.human}` перед `round.running` в `BottomBar`;
  `onreveal`/`ondone` → `system.reveal_browser`/`system.human_done`; условие
  `step.stage === 'aggregator'` в `moved`; подписка `round_note` → `say`.
- `card_finish.test.js`: `|| held(done)` в `cardFinish`.
- `channels.test.js` (новые два): `muted: !enabled`, `dim: … || !enabled`, ветка
  `MASTER_OFF_TITLE` в `sourceToggle`.
- `contact_adding.test.js`: `catch → trouble = refusal.message`, сброс `trouble` в сеттере
  `adding`, `finally { saving = false }`, `|| saving` в заслоне, `form.done(draft, done)`,
  `list.again(done)`.
- `contacts_watch.test.js`: порядок `forget()` → `read(id)`, подписка
  `vacancies_list_changed`, `deaf()` в снятии.
- `footer.test.js`: тернарий `need.kind === 'captcha'` в `humanText`.
- `new_card.test.js`: `ONE_FIELD.named` (`trim`), ветки `created`/`status === 'created'` в `done`.
- `paging.test.js`: `card !== null && nearBottom(...)` в `detailScrolled`.
- `profile.test.js`: `.replace(/\s/g, '')` в `profileSheet`, копии `[...grades]`/`[...formats]`.
- `provider_form.test.js`: `if (alive.now)` в `listModels`; `forget()` в `pickPreset`;
  сброс `same`/`models` в `switchSource` и заслон `toFile === fromFile`; условие
  `got.path && !got.trouble` и ранний выход по `alive` в `pickFile`; `mirrored` в
  `useChat`; `probe.status !== 'busy'` в `verify`; тернарий `trouble`.
- `round.test.js`: `if (was)` в `ingestion_finished`, `finishers.delete`, `human = null` в
  `ingestion_finished` и `human_resolved`.
- `settings.test.js`: ветки `probeLine`; `canShareChat(chat)` в `embedReading`.
- `settings_screen_live.test.js`: слияние `aggregator_backfill_limit` в `refresh`;
  `BOUNDS.aggregator_backfill_limit` (зажим до 500); `mailPill` (`address && password &&
  smtp_host`); `mailNeedsServer` (`!server_by_address`); `readMail()` после
  `settings.save_mail`; `onhelp` в `SecretInput`; `onopen(url)` в `MailPasswordHelp`;
  `actions={…}` в `SettingsSection`. Исключение — «строки о сеансе нет» (п. 9 выше).
- `site.test.js`: перенесённые без изменений проверки `siteHref`.
- `source_card.test.js`: `forget` (`card = null`, `vacancies.clear()`), `show: … trouble`,
  `vacanciesOf(id)` в `more`/`reread`.
- `source_list.test.js`: `fresh(...)` в `again`, `search = text` в `find`,
  `result !== null` в `switched`, `entered`.
- `source_row_live.test.js`: `onclick={() => onpick()}` на всей строке;
  `event.target === event.currentTarget` в `onkeydown`.
- `source_vacancies.test.js`: `offset: rows.length` и `appended` в `more`, `!hasMore ||
  digging`, `refreshLimit(rows.length)` в `reload`, `fresh` против гонки, `clear`.
- `sources.test.js`: `share` (прочерк против процента), `!stats.total`, тернарий в
  `masterToggle`. С оговоркой из п. 10 выше.
- `stats.test.js`: `SOURCE_ROW.aggregator`/`channel`/`none`, ключ
  `${kind}:${id ?? aggregator_id ?? ''}`.
- `stats_channels_card_live.test.js`: `opens = one.target !== null`, `onpick(row.target)`,
  `{#each rows as row (row.key)}`.
- `tg_login_dialog_live.test.js`: ветка `{#if asking.secret}` с `SecretInput`,
  `onsave={(typed) => (value = typed)}`.
- `vacancies.test.js` и `vacancies_screen_new_live.test.js`: `typed(draft) && running` в
  `pasteLock`; `busy={busy || Boolean(locked)}` и `busyLabel={locked || …}` в `NewCardDialog`.
- `vacancy_actions.test.js`: `send: busy` (больше без `card.hr`), `running ? RUNNING`,
  ветки `sourcePill`/`siteName`, порядок `viaTelegram` и `viaAgent` и `found.lock ? []` в
  `applyChoices`, ключ `${method} ${target}`, условие `noChoiceReason`.
- `vacancy_apply_live.test.js`: `rows.length === 1 → send(rows[0])`, `row.way ?
  apply_via : send_application`, `ready={chosen !== null}`, `id !== vacancyId` в `respond`,
  `blocks.send` от `round.running`.
- `vacancy_card.test.js`: `EVENT_TEXT.found` (`web_search`), `appliedNote` (`WRITER`,
  `simulated`), `apply_failed`, `vacancy_closed`.
- `vacancy_card_live.test.js` (новый): `onclick={() => copy(card.title, …)}` на `.det-title`.
- `vacancy_contacts.test.js`: `KEPT_RE`, `EMAIL_RE`, `PHONE_RE`, замена `[^\d+]` и откат на `siteHref`.
- `vacancy_screening_live.test.js`: положение `MenuItem «Скрининг»` между raw и источником,
  `disabled={!screened}`, `class:me={line.from_us}`, `id !== vacancyId` в `showScreening`.
- `words.test.js`: формы в `vacancyCount` через `plural`.

## Declined to judge

- Длина файлов `SettingsScreen.svelte`, `VacancyCard.svelte` и `AggregatorCard.svelte`: правило 4 держит машина, а не моё измерение.
- `say: () => {}` в `VacancyContactsSection.svelte:21`: это вопрос поведения или «ничего на всякий случай» (п. 8), он вне моего измерения. К тому же форма `contact` и так отдаёт пустое слово.
- `call` напрямую вместо `ask` в `AggregatorsList`, `ChannelsList`, `VacancyContactsSection`: сборкам `api` разрешён, а решение предметного отказа в окне объяснено в `contact_adding`.
- Импорт через алиас `$state/…` внутри слоя `state` (`source_card`, `source_list`, `source_vacancies`) при `./…` у соседей: это стиль, а не правило манифеста.
- Литералы текста в тестах чистых функций (`humanText`, `vacancyCount`, `masterToggle` и др.): для функции, чей результат — сама показанная строка, это и есть наблюдаемое следствие. Оговорка только об именах (п. 10).
- Два комментария подряд над `.det-title` в `styles/vacancy-card.css:25-28`: оба объясняют разные решения, неточности в них нет.
- Названия `StatsChannelsCard`/`channelRows`/`stats-channels.css` при содержимом «источники»: это переименование, оно не входит в мои правила. Неверный комментарий отмечен отдельно (п. 8).
- Соответствие спеке и пропуски функционала: это не моё измерение.
- Правило 16 (что читалось при работе): по диффу его не наблюдать, пропускаю, как велено.
- Мутационная проверка «краснеет ли тест за свою строку»: прогонять тесты и менять код мне запрещено. Строки названы словами (раздел п. 14).

## Assessment

**Ready to merge?** With fixes

**Reasoning:** Слои соблюдены. Компоненты не читают общее состояние, повторы вынесены, логика ушла из сборок в `state`. Важная правка одна: `watchSourceCard` лежит в модуле захода на вкладки, и его шапка говорит неправду. Остальное мелочи: оформление в чужом файле, устаревшие счёты в комментариях, один тест, который не может упасть.

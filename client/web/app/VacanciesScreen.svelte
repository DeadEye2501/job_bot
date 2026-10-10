<script>
  // Раздел «Вакансии»: список с поиском, порядком, отбором и страницами.

  import { untrack } from 'svelte';

  import NewCardDialog from '$components/NewCardDialog.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import VacancyFilters from '$components/VacancyFilters.svelte';
  import VacancyRow from '$components/VacancyRow.svelte';

  import VacancyCard from './VacancyCard.svelte';
  import { living } from '$state/alive.js';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { freshAnswer } from '$state/fresh.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { companyTitle } from '$state/companies.js';
  import { personName } from '$state/people.js';
  import { labels, sameName } from '$state/picker.js';
  import { whileOpen } from '$state/outside.js';
  import { round } from '$state/round.svelte.js';
  import { VACANCY_PAGE, appended, nearBottom, refreshLimit } from '$state/paging.js';
  import { filterPayload } from '$state/vacancy_filter.js';
  import { vacancyView } from '$state/vacancy_view.svelte.js';
  import {
    SORTS,
    emptyNote,
    pasteLock,
    sortKey,
    typed,
    vacancyFields,
  } from '$state/vacancies.js';

  // `lockedTip` приходит сверху, а не спрашивается здесь: лампы состояния
  // опрашивает оболочка для нижней полосы, и второй опрос из карточки дал бы
  // две разные правды об одном.
  let { ask, say, lockedTip, events, oncontacts, open, onopened, openFilter, onfiltered } =
    $props();

  let loaded = $state(false);
  let rows = $state([]);
  let hasMore = $state(false);
  let loadingMore = $state(false);
  let search = $state('');
  let threshold = $state(null);
  let opened = $state(null);
  // Меню порядка и панель отбора взаимно гасят друг друга: обе падают из одной
  // полосы, и открытые разом они накрывают одна другую.
  let sortOpen = $state(false);
  let filterOpen = $state(false);
  // Полоса над списком: по ней меню порядка считает «нажали мимо». Своим узлом
  // ему годится только она — кнопка, которой его открывают, лежит рядом с
  // меню, а не внутри него.
  let bar = $state(null);
  // Границы срока замораживаются в миг применения: пересчитай их к следующей
  // странице, скользящее окно «за неделю» уехало бы вперёд, а `offset`
  // считался бы по уже другой выдаче — строки на стыке страниц пропали бы.
  // Заход в раздел — тот же миг применения: отбор человек оставил прошлый, а
  // «за неделю» отсчитывается от того, когда он на список смотрит.
  let asked = $state(filterPayload(vacancyView.filter, new Date()));
  // Каналы и компании для панели собраны мимо действующего отбора: считай их
  // мост по выдаче, меню сжималось бы до того, что уже отобрано, и вернуть
  // отброшенное было бы нечем. Спрашиваются своим зовом — `askOptions`.
  let options = $state({ channels: [], companies: [] });
  // Дошли ли перечни хоть раз. Сорвавшийся зов иначе оставил бы меню пустым
  // навсегда: спрашивают их не на каждом чтении списка, а при открытии экрана и
  // на вести о правке, — и вернуть их человеку было бы нечем ни поиском, ни
  // отбором.
  let optionsLoaded = $state(false);

  const alive = living();
  const fresh = freshAnswer(() => alive.now);
  // Свой счёт попыток: перечни спрашивают и открытие экрана, и весть о правке
  // списка, а ответы возвращаются вразнобой — лёгший поверх свежего старый убрал
  // бы из меню только что заведённую компанию.
  const freshOptions = freshAnswer(() => alive.now);

  // Заведение руками. Обвязка та же, что у людей и компаний: черновик,
  // заслон пустого названия, гашение окна только по удаче.
  //
  // Список перечитывается показанным числом строк, а не страницей: заведение
  // не повод схлопывать пролистанное — тот же довод, что и у вести о правке.
  const newCard = contactAdding({
    list: { again: () => refresh(refreshLimit(rows.length, VACANCY_PAGE)) },
    form: NEW_CARD.vacancy,
    // Слот выбирается способом заведения: набранные поля ложатся в строку как
    // есть, а вставленный текст уходит в конвейер на разбор — и оттуда
    // возвращается баллом, приговором и заполненными полями. Имена слотов
    // стоят литералами на самом шве: спрятанные в таблицу, они выпали бы
    // из-под сторожа договора страницы.
    save: (draft) =>
      typed(draft)
        ? ask('vacancies.create_from_text', {
            raw_text: draft.raw_text,
            posted_at: draft.posted_at,
          })
        : ask('vacancies.create', vacancyFields(draft)),
    say: (text) => say(text),
  });

  // Кого предложить компанией и HR-ом в форме заведения. Спрашиваются при
  // открытии окна, а не вместе с экраном: список вакансий их не показывает, а
  // карточек в базе бывают сотни — заезжай они с каждым чтением списка,
  // человек платил бы за них на каждый набранный в поиске знак.
  let linkOptions = $state({ companies: [], hrs: [] });

  // Чем стороны формы отличаются друг от друга: парой полей черновика — номером
  // для моста и именем для поля — и тем, кто умеет назвать запись. Больше
  // ничем, и написанные двумя телами, они разошлись бы молча.
  //
  // Имени слота моста здесь нет нарочно: оно пишется литералом на самом шве
  // (`makeSide` ниже), а спрятанное в таблицу выпадает из-под сторожей
  // договора страницы и молча переживает переименование.
  const SIDES = {
    companies: { id: 'company_id', name: 'company_name', named: (row) => companyTitle(row).name },
    hrs: { id: 'hr_id', name: 'hr_name', named: personName },
  };

  // Полю с подсказкой уезжают подписи: номер карточки человеку не о чем
  // сравнивать с тем, что он набрал, а тёзок различает ник в подписи.
  const suggestions = $derived({
    companies: labels(linkOptions.companies, SIDES.companies.named),
    hrs: labels(linkOptions.hrs, SIDES.hrs.named),
  });

  /** Открыть окно заведения и спросить перечни для его подборщиков.
   *
   * Окно открывается сразу, не дожидаясь перечней: набирать название человек
   * начинает раньше, чем доедут сотни карточек, а подборщики до ответа стоят
   * пустыми и говорят об этом сами.
   */
  async function openNew() {
    newCard.adding = true;
    const now = await ask('vacancies.create_options');
    if (now === null) return;
    linkOptions = now;
  }

  /** Принять набранное в поле стороны: знакомую узнать, незнакомую завести.
   *
   * Заводится сразу, без второго вопроса: вакансию заводят по объявлению, и
   * той компании в базе обычно ещё нет — отправь форма человека заводить её на
   * соседний экран, он вернулся бы к пустому черновику.
   *
   * Имя остаётся в поле и при неудаче: набранное человеком не стирается
   * ответом моста, а о беде он уже прочёл плашкой.
   */
  async function settle(side, typed) {
    const { id, name, named } = SIDES[side];
    // Черновик запоминается свой: пока летит заведение, окно могли закрыть, и
    // тогда на его месте стоит уже чистый — номер, положенный в него, достался
    // бы следующей вакансии.
    const mine = newCard.draft;
    mine[name] = typed;
    // Связь снимается сразу: набрано другое имя, и прежний номер до нового
    // подтверждения не значит ничего. Останься он — отказ моста оставил бы
    // вакансию привязанной к той карточке, которую человек уже сменил.
    mine[id] = null;
    if (!typed) return;
    const known = sameName(linkOptions[side], typed, named);
    if (known !== null) {
      mine[id] = known.id;
      return;
    }
    const made = await makeSide(side, typed);
    if (made === null || newCard.draft !== mine) return;
    mine[id] = made.created_id;
    linkOptions = {
      ...linkOptions,
      [side]: [...linkOptions[side], { id: made.created_id, name: typed }],
    };
  }

  /** Завести незнакомую сторону и назвать её номер.
   *
   * Зовы моста написаны литералами обеими ветками: имя метода должно быть
   * видно на шве, а собранное из кусков там не видно вовсе — ни человеку, ни
   * сторожам договора страницы.
   */
  function makeSide(side, name) {
    return side === 'companies'
      ? ask('companies.create', { name })
      : ask('hr.create', { name });
  }

  // Какую вакансию открыть, придя со стороны — из мини-списка в карточке
  // канала, компании или человека.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  // С каким отбором открыть список, придя из статистики. Поиск и открытая
  // карточка при этом снимаются: человек просил список этого статуса, а не
  // пересечение его с тем, что искал час назад.
  $effect(() => {
    if (!openFilter) return;
    const wanted = openFilter.filter;
    search = '';
    opened = null;
    // Вне слежения: `apply` перечитывает список, а тот читает поиск и порядок —
    // следящий эффект заводился бы заново на каждом набранном знаке и навязывал
    // бы отбор статистики поверх того, что человек уже успел выбрать.
    untrack(() => apply(wanted));
    onfiltered();
  });

  /** Перечитать список с начала.
   *
   * Свой счёт попыток: человек набирает поиск посимвольно и меняет порядок, а
   * ответы возвращаются вразнобой — лёгший поверх свежего старый показал бы
   * строки, которых он уже не ищет.
   *
   * Потолок — довод: по вести о новых вакансиях список перечитывается тем
   * числом строк, которое уже показано.
   */
  async function refresh(limit = VACANCY_PAGE) {
    const now = await fresh(() =>
      ask('vacancies.list', {
        search,
        sort: sortKey(vacancyView.sort),
        limit,
        offset: 0,
        ...asked,
      }),
    );
    if (now === null) return;
    rows = now.vacancies;
    hasMore = now.has_more;
    // Порог отбора приезжает вместе со списком: по нему красится оценка, и
    // спрашивать его отдельно значило бы ждать второго ответа ради цвета.
    threshold = now.score_threshold;
    loaded = true;
    // Не дошедшие перечни просим ещё раз. Только не дошедшие ни разу: иначе
    // каждый набранный в поиске знак снова тянул бы за собой полный проход по
    // таблице — ровно то, ради чего их и вынесли из ответа списка.
    if (!optionsLoaded) askOptions();
  }

  /** Перечни для меню отбора: все каналы и все компании.
   *
   * Своим зовом, не вместе со списком: от поиска и страницы они не зависят, а
   * список перечитывается на каждое нажатие клавиши — приезжай перечни с ним,
   * каждый знак стоил бы лишнего полного прохода по таблице вакансий.
   */
  async function askOptions() {
    const now = await freshOptions(() => ask('vacancies.filter_options'));
    if (now === null) return;
    options = now.filter_options;
    optionsLoaded = true;
  }

  /** Дочитать следующую страницу.
   *
   * Своей попытки не берёт: она объявила бы устаревшим уже идущее
   * перечитывание, а свежее как раз оно. Вместо счёта сверяется само основание
   * — тот ли поиск, порядок и отбор и тот ли список, к концу которого страницу
   * дописывают: перечитывание кладёт другой список, и дописывать доехавшую
   * страницу становится некуда.
   */
  async function more() {
    const was = { search, sort: sortKey(vacancyView.sort), filter: asked, rows };
    const page = await ask('vacancies.list', {
      search: was.search,
      sort: was.sort,
      limit: VACANCY_PAGE,
      offset: was.rows.length,
      ...was.filter,
    });
    if (page === null || !alive.now) return;
    if (rows !== was.rows || search !== was.search) return;
    if (sortKey(vacancyView.sort) !== was.sort || asked !== was.filter) return;
    rows = appended(rows, page.vacancies);
    hasMore = page.has_more;
  }

  /** Догрузить, когда список подъехал к низу.
   *
   * Одна страница за раз: прокрутка сыплет событиями десятками в секунду, и
   * без запора на уже идущий зов мост получил бы их все.
   */
  function scrolled(event) {
    if (!hasMore || loadingMore) return;
    if (!nearBottom(event.currentTarget)) return;
    loadingMore = true;
    more().finally(() => {
      loadingMore = false;
    });
  }

  function find(text) {
    search = text;
    return refresh();
  }

  function order(label) {
    vacancyView.sort = label;
    sortOpen = false;
    return refresh();
  }

  function apply(next) {
    vacancyView.filter = next;
    asked = filterPayload(next, new Date());
    return refresh();
  }

  $effect(() => {
    // Нажатие мимо закрывает меню. Оно падает поверх списка, и оставленное
    // открытым закрывает собой те самые строки, ради которых порядок меняли.
    return whileOpen(sortOpen, () => bar, () => (sortOpen = false));
  });

  $effect(() => {
    // Список меняет не только этот экран: бот собирает вакансии сам, и статусы
    // им же двигаются по ходу переписки.
    // Перечитываем показанным числом строк, а не страницей: весть приходит на
    // каждый разобранный кусок обхода, и страницей она схлопывала бы
    // пролистанное снова и снова.
    // Перечни для меню спрашиваются той же вестью: новая вакансия приносит с
    // собой и новую компанию, и новый канал.
    const deaf = events.on('vacancies_list_changed', () => {
      askOptions();
      return refresh(refreshLimit(rows.length, VACANCY_PAGE));
    });
    const settled = alive.entered(() => {
      askOptions();
      refresh();
    });
    return () => {
      settled();
      deaf();
    };
  });
</script>

<div class="vacancies-layout">
  <section class="vac-list-pane">
    <div class="bar vac-list-toolbar" bind:this={bar}>
      <SearchBox value={search} placeholder="Поиск" onsearch={find} />

      <button
        class="icon-btn"
        type="button"
        title="Добавить вакансию"
        onclick={() => openNew()}
      >
        <span class="material-symbols-outlined">{NEW_CARD.vacancy.icon}</span>
      </button>

      <button
        class="icon-btn"
        type="button"
        title="Сортировка: {vacancyView.sort}"
        onclick={() => {
          sortOpen = !sortOpen;
          filterOpen = false;
        }}
      >
        <span class="material-symbols-outlined">swap_vert</span>
      </button>

      <VacancyFilters
        applied={vacancyView.filter}
        {options}
        onapply={apply}
        shown={filterOpen}
        onshown={(next) => {
          filterOpen = next;
          if (next) sortOpen = false;
        }}
      />

      {#if sortOpen}
        <div class="vac-sort-menu">
          {#each SORTS as one (one.key)}
            <button
              class="vac-sort-option"
              class:active={vacancyView.sort === one.label}
              type="button"
              onclick={() => order(one.label)}
            >
              {one.label}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <div class="vac-list" onscroll={scrolled}>
      {#if !loaded}
        <div class="empty-note vac-list-empty">Загрузка…</div>
      {:else if rows.length === 0}
        {@const note = emptyNote(search)}
        <div class="empty-note vac-list-empty">
          <span class="material-symbols-outlined">{note.icon}</span>
          <span>{note.text}</span>
        </div>
      {:else}
        {#each rows as vacancy (vacancy.id)}
          <VacancyRow
            {vacancy}
            {threshold}
            selected={opened === vacancy.id}
            onpick={() => (opened = vacancy.id)}
          />
        {/each}
      {/if}
    </div>
  </section>

  <section class="vac-detail-pane">
    {#if opened === null}
      <div class="empty-note vac-detail-empty">Выберите вакансию слева</div>
    {:else}
      <VacancyCard
        {ask}
        {say}
        {events}
        {lockedTip}
        {oncontacts}
        vacancyId={opened}
        onclose={() => (opened = null)}
        onchanged={() => refresh(refreshLimit(rows.length, VACANCY_PAGE))}
      />
    {/if}
  </section>
</div>

{#if newCard.adding}
  <NewCardDialog
    kind="vacancy"
    draft={newCard.draft}
    busy={newCard.saving}
    ready={newCard.ready}
    locked={pasteLock(newCard.draft, round.running)}
    options={suggestions}
    oncompany={(typed) => settle('companies', typed)}
    onhr={(typed) => settle('hrs', typed)}
    onconfirm={() => newCard.create()}
    oncancel={() => (newCard.adding = false)}
  />
{/if}

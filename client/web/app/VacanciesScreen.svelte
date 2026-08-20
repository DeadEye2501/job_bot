<script>
  // Раздел «Вакансии»: список с поиском, порядком, отбором и страницами.

  import { untrack } from 'svelte';

  import SearchBox from '$components/SearchBox.svelte';
  import VacancyFilters from '$components/VacancyFilters.svelte';
  import VacancyRow from '$components/VacancyRow.svelte';

  import VacancyCard from './VacancyCard.svelte';
  import { attempts } from '$state/attempts.js';
  import { VACANCY_PAGE, appended, nearBottom, refreshLimit } from '$state/paging.js';
  import { blankFilter, filterPayload } from '$state/vacancy_filter.js';
  import { SORTS, emptyNote, sortKey } from '$state/vacancies.js';

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
  let sort = $state(SORTS[0].label);
  let threshold = $state(null);
  let opened = $state(null);
  // Меню порядка и панель отбора взаимно гасят друг друга: обе падают из одной
  // полосы, и открытые разом они накрывают одна другую.
  let sortOpen = $state(false);
  let filterOpen = $state(false);
  let applied = $state(blankFilter());
  // Границы срока замораживаются в миг применения: пересчитай их к следующей
  // странице, скользящее окно «за неделю» уехало бы вперёд, а `offset`
  // считался бы по уже другой выдаче — строки на стыке страниц пропали бы.
  let asked = $state({});
  // Каналы и компании для панели собраны мимо действующего отбора: считай их
  // мост по выдаче, меню сжималось бы до того, что уже отобрано, и вернуть
  // отброшенное было бы нечем. Спрашиваются своим зовом — `askOptions`.
  let options = $state({ channels: [], companies: [] });
  // Дошли ли перечни хоть раз. Сорвавшийся зов иначе оставил бы меню пустым
  // навсегда: спрашивают их не на каждом чтении списка, а при открытии экрана и
  // на вести о правке, — и вернуть их человеку было бы нечем ни поиском, ни
  // отбором.
  let optionsLoaded = $state(false);

  const tries = attempts();
  // Свой счёт попыток: перечни спрашивают и открытие экрана, и весть о правке
  // списка, а ответы возвращаются вразнобой — лёгший поверх свежего старый убрал
  // бы из меню только что заведённую компанию.
  const optionTries = attempts();
  let alive = true;

  // Какую вакансию открыть, придя со стороны — из мини-списка в карточке
  // канала, компании или человека. Отметка гасится сразу: раздел открывают и
  // просто так, и заново открытая карточка вакансии, которую уже закрыли,
  // читалась бы как поломка.
  $effect(() => {
    if (!open) return;
    opened = open.id;
    onopened();
  });

  // С каким отбором открыть список, придя из статистики. Поиск и открытая
  // карточка при этом снимаются: человек просил список этого статуса, а не
  // пересечение его с тем, что искал час назад.
  $effect(() => {
    if (!openFilter) return;
    const asked = openFilter.filter;
    search = '';
    opened = null;
    // Вне слежения: `apply` перечитывает список, а тот читает поиск и порядок —
    // следящий эффект заводился бы заново на каждом набранном знаке и навязывал
    // бы отбор статистики поверх того, что человек уже успел выбрать.
    untrack(() => apply(asked));
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
    const mine = tries.next();
    // Идущая догрузка этим зовом обесценена: её ответ уже не ляжет, и держать
    // по ней запор значит молча не догружать свежий список до самого ответа.
    loadingMore = false;
    const now = await ask('vacancies.list', {
      search,
      sort: sortKey(sort),
      limit,
      offset: 0,
      ...asked,
    });
    if (now === null || !alive || tries.stale(mine)) return;
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
    const mine = optionTries.next();
    const now = await ask('vacancies.filter_options');
    if (now === null || !alive || optionTries.stale(mine)) return;
    options = now.filter_options;
    optionsLoaded = true;
  }

  async function more() {
    const mine = tries.next();
    const page = await ask('vacancies.list', {
      search,
      sort: sortKey(sort),
      limit: VACANCY_PAGE,
      offset: rows.length,
      ...asked,
    });
    if (page === null || !alive || tries.stale(mine)) return;
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
    sort = label;
    sortOpen = false;
    return refresh();
  }

  function apply(next) {
    applied = next;
    asked = filterPayload(next, new Date());
    return refresh();
  }

  $effect(() => {
    if (!sortOpen) return;
    // Нажатие мимо закрывает меню. Оно падает поверх списка, и оставленное
    // открытым закрывает собой те самые строки, ради которых порядок меняли.
    const away = (event) => {
      if (!event.target.closest('.vac-list-toolbar')) sortOpen = false;
    };
    document.addEventListener('click', away);
    return () => document.removeEventListener('click', away);
  });

  $effect(() => {
    alive = true;
    // Список меняет не только этот экран: бот собирает вакансии сам, и статусы
    // им же двигаются по ходу переписки.
    // Перечитываем показанным числом строк, а не страницей: весть приходит на
    // каждый разобранный кусок обхода, и страницей она схлопывала бы
    // пролистанное снова и снова.
    // Перечни для меню спрашиваются той же вестью: новая вакансия приносит с
    // собой и новую компанию, и новый канал.
    const deaf = events.on('vacancies_list_changed', () => {
      askOptions();
      return refresh(refreshLimit(rows.length));
    });
    // Первое чтение — вне слежения: поиск и порядок `refresh` читает, и следящий
    // эффект перезаводился бы на каждом набранном знаке.
    untrack(() => {
      askOptions();
      refresh();
    });
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

<div class="vacancies-layout">
  <section class="vac-list-pane">
    <div class="vac-list-toolbar">
      <SearchBox value={search} placeholder="Поиск" onsearch={find} />

      <button
        class="icon-btn"
        type="button"
        title="Сортировка: {sort}"
        onclick={() => {
          sortOpen = !sortOpen;
          filterOpen = false;
        }}
      >
        <span class="material-symbols-outlined">swap_vert</span>
      </button>

      <VacancyFilters
        {applied}
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
              class:active={sort === one.label}
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
        <div class="vac-list-empty">Загрузка…</div>
      {:else if rows.length === 0}
        {@const note = emptyNote(search)}
        <div class="vac-list-empty">
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
      <div class="vac-detail-empty">Выберите вакансию слева</div>
    {:else}
      <VacancyCard
        {ask}
        {say}
        {events}
        {lockedTip}
        {oncontacts}
        vacancyId={opened}
        onclose={() => (opened = null)}
        onchanged={() => refresh(refreshLimit(rows.length))}
      />
    {/if}
  </section>
</div>

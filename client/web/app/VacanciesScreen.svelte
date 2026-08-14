<script>
  // Раздел «Вакансии»: список с поиском, порядком, отбором и страницами.

  import { untrack } from 'svelte';

  import Dropdown from '$components/Dropdown.svelte';
  import SearchList from '$components/SearchList.svelte';
  import VacancyFilters from '$components/VacancyFilters.svelte';
  import VacancyRow from '$components/VacancyRow.svelte';
  import { attempts } from '$state/attempts.js';
  import { PAGE, appended, refreshLimit } from '$state/paging.js';
  import { blankFilter, filterPayload } from '$state/vacancy_filter.js';
  import { SORTS, sortKey } from '$state/vacancies.js';

  let { ask, events } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let hasMore = $state(false);
  let search = $state('');
  let sort = $state(SORTS[0].label);
  let threshold = $state(null);
  let applied = $state(blankFilter());
  // Границы срока замораживаются в миг применения: пересчитай их к следующей
  // странице, скользящее окно «за неделю» уехало бы вперёд, а `offset`
  // считался бы по уже другой выдаче — строки на стыке страниц пропали бы.
  let asked = $state({});
  // Каналы и компании для панели собраны мимо действующего отбора: считай их
  // мост по выдаче, меню сжималось бы до того, что уже отобрано, и вернуть
  // отброшенное было бы нечем.
  let options = $state({ channels: [], companies: [] });

  const tries = attempts();
  let alive = true;

  /** Перечитать список с начала.
   *
   * Свой счёт попыток: человек набирает поиск посимвольно и меняет порядок, а
   * ответы возвращаются вразнобой — лёгший поверх свежего старый показал бы
   * строки, которых он уже не ищет.
   *
   * Потолок — довод: по вести о новых вакансиях список перечитывается тем
   * числом строк, которое уже показано.
   */
  async function refresh(limit = PAGE) {
    const mine = tries.next();
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
    options = now.filter_options;
    // Порог отбора приезжает вместе со списком: по нему красится оценка, и
    // спрашивать его отдельно значило бы ждать второго ответа ради цвета.
    threshold = now.score_threshold;
    loaded = true;
  }

  async function more() {
    const mine = tries.next();
    const page = await ask('vacancies.list', {
      search,
      sort: sortKey(sort),
      limit: PAGE,
      offset: rows.length,
      ...asked,
    });
    if (page === null || !alive || tries.stale(mine)) return;
    rows = appended(rows, page.vacancies);
    hasMore = page.has_more;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  function order(label) {
    sort = label;
    return refresh();
  }

  function apply(next) {
    applied = next;
    asked = filterPayload(next, new Date());
    return refresh();
  }

  $effect(() => {
    alive = true;
    // Список меняет не только этот экран: бот собирает вакансии сам, и статусы
    // им же двигаются по ходу переписки.
    // Перечитываем показанным числом строк, а не страницей: весть приходит на
    // каждый разобранный кусок обхода, и страницей она схлопывала бы
    // пролистанное снова и снова.
    const deaf = events.on('vacancies_list_changed', () => refresh(refreshLimit(rows.length)));
    // Первое чтение — вне слежения: поиск и порядок `refresh` читает, и следящий
    // эффект перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

<div class="screen-body">
  <SearchList
    {search}
    placeholder="Поиск по названию, описанию, компании, стеку"
    onsearch={find}
    {loaded}
    count={rows.length}
    words={['вакансия', 'вакансии', 'вакансий']}
    filtered={!!search || Object.keys(asked).length > 0}
    nothing="Ничего не найдено"
    empty="Вакансий пока нет — они появятся после первого обхода каналов"
  >
    {#snippet actions()}
      <Dropdown options={SORTS.map((one) => one.label)} value={sort} onpick={order} />
      <VacancyFilters {applied} {options} onapply={apply} />
    {/snippet}

    {#each rows as vacancy (vacancy.id)}
      <VacancyRow {vacancy} {threshold} />
    {/each}

    {#if hasMore}
      <button class="add-more" type="button" onclick={more}>Показать ещё</button>
    {/if}
  </SearchList>
</div>

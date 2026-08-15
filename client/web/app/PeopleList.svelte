<script>
  // Вкладка «HR»: список людей с поиском, страницами и заведением.

  import { untrack } from 'svelte';

  import AskDialog from '$components/AskDialog.svelte';
  import NewPersonFields from '$components/NewPersonFields.svelte';
  import PersonRow from '$components/PersonRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { attempts } from '$state/attempts.js';
  import { named } from '$state/contacts.js';
  import { PAGE, appended, nearBottom, refreshLimit } from '$state/paging.js';

  import PersonCard from './PersonCard.svelte';

  let { ask, say, events, open, onopened, oncompany, onvacancy } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let hasMore = $state(false);
  let search = $state('');
  let adding = $state(false);
  let draft = $state({ name: '', telegram_username: '', telegram_user_id: '', notes: '' });
  let opened = $state(null);
  let loadingMore = $state(false);

  const tries = attempts();
  let alive = true;

  // Кого открыть, придя со стороны — из списка непрочитанного над полосой или
  // из карточки вакансии. Отметка гасится сразу: вкладку открывают и просто
  // так, и заново открытая карточка человека, которого уже закрыли, читалась бы
  // как поломка.
  $effect(() => {
    if (!open) return;
    opened = open.id;
    onopened();
  });

  /** Перечитать список с начала.
   *
   * Потолок шлём всегда: у этого перечня на мосту умолчания нет вовсе, и без
   * потолка он отдал бы всех разом. Потолок при этом довод — перечитывают
   * список и после правки в карточке, где показанного больше страницы.
   */
  async function refresh(limit = PAGE) {
    const mine = tries.next();
    const now = await ask('hr.list', { search, limit, offset: 0 });
    if (now === null || !alive || tries.stale(mine)) return;
    rows = now.hrs;
    hasMore = now.has_more;
    loaded = true;
  }

  async function more() {
    const mine = tries.next();
    const page = await ask('hr.list', { search, limit: PAGE, offset: rows.length });
    if (page === null || !alive || tries.stale(mine)) return;
    rows = appended(rows, page.hrs);
    hasMore = page.has_more;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  /** Дочитать следующую страницу, когда список подошёл к концу.
   *
   * Прокруткой, а не кнопкой: список читают сверху вниз и глазами, а кнопка
   * посреди чтения заставляет целиться в неё мышью.
   */
  function scrolled(event) {
    if (!hasMore || loadingMore || !nearBottom(event.currentTarget)) return;
    loadingMore = true;
    more().finally(() => {
      loadingMore = false;
    });
  }

  /** Завести человека.
   *
   * Заслон один — назвать хоть чем-нибудь: карточка без имени, ника и номера
   * учётной записи не находится потом ни поиском, ни отправкой. Негодный ник
   * отбивает мост, и его отказ приезжает плашкой.
   */
  async function create() {
    if (!named(draft)) return;
    const done = await ask('hr.create', { ...draft });
    // Окно закрываем только по удаче: отказ — это чаще всего опечатка в нике,
    // и набранное человеку ещё пригодится.
    if (done === null) return;
    adding = false;
    draft = { name: '', telegram_username: '', telegram_user_id: '', notes: '' };
    say('Карточка заведена');
    return refresh(refreshLimit(rows.length));
  }

  $effect(() => {
    alive = true;
    // Списки меняет не только этот экран: бот заводит людей сам, разбирая
    // переписку, и он же считает непрочитанное.
    // Только про списки: весть о непрочитанном кладётся на каждое сохранённое
    // письмо, и обход в сотню сообщений перечитал бы список сотню раз подряд.
    const deaf = events.on('contacts_lists_changed', () => refresh(refreshLimit(rows.length)));
    // Первое чтение — вне слежения: строку поиска `refresh` читает, и следящий
    // эффект перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

<div class="cnt-layout">
  <section class="cnt-list-pane">
    <div class="cnt-list-toolbar">
      <SearchBox value={search} placeholder="Поиск по имени, @username..." onsearch={find} />
      <button
        class="cnt-add-btn"
        type="button"
        title="Добавить HR"
        onclick={() => (adding = true)}
      >
        <span class="material-symbols-outlined">person_add</span>
      </button>
    </div>

    <div class="cnt-list" onscroll={scrolled}>
      {#if !loaded}
        <div class="cnt-list-empty">Загрузка…</div>
      {:else if rows.length === 0}
        <div class="cnt-list-empty">
          {#if search}
            Никого не найдено по запросу «{search}».
          {:else}
            HR'ов пока нет.<br />Нажмите кнопку добавления вверху, чтобы создать первого.
          {/if}
        </div>
      {:else}
        {#each rows as person (person.id)}
          <PersonRow
            {person}
            selected={opened === person.id}
            onpick={() => (opened = person.id)}
          />
        {/each}
      {/if}
    </div>
  </section>

  <section class="cnt-detail-pane">
    {#if opened === null}
      <div class="cnt-detail-empty">Выберите HR в списке слева</div>
    {:else}
      <PersonCard
        {ask}
        {say}
        {events}
        {oncompany}
        {onvacancy}
        personId={opened}
        onclose={() => (opened = null)}
        onchanged={() => refresh(refreshLimit(rows.length))}
      />
    {/if}
  </section>
</div>

{#if adding}
  <AskDialog
    icon="person_add"
    title="Новый человек"
    subtitle="Хотя бы имя, ник или номер учётной записи — иначе карточку потом не найти."
    confirmLabel="Создать"
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <NewPersonFields {draft} />
  </AskDialog>
{/if}

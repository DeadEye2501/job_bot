<script>
  // Вкладка «HR»: список людей с поиском, страницами и заведением.

  import { untrack } from 'svelte';

  import AskDialog from '$components/AskDialog.svelte';
  import NewPersonFields from '$components/NewPersonFields.svelte';
  import PersonRow from '$components/PersonRow.svelte';
  import SearchList from '$components/SearchList.svelte';
  import { attempts } from '$state/attempts.js';
  import { named } from '$state/contacts.js';
  import { PAGE, appended, refreshLimit } from '$state/paging.js';

  import PersonCard from './PersonCard.svelte';

  let { ask, say, events, openPerson, onopened } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let hasMore = $state(false);
  let search = $state('');
  let adding = $state(false);
  let draft = $state({ name: '', telegram_username: '', telegram_user_id: '', notes: '' });
  let opened = $state(null);

  const tries = attempts();
  let alive = true;

  // Кого открыть, придя со стороны — из списка непрочитанного над полосой.
  // Отметка гасится сразу: вкладку открывают и просто так, и заново открытая
  // карточка человека, которого уже закрыли, читалась бы как поломка.
  $effect(() => {
    if (!openPerson) return;
    opened = openPerson.id;
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

<SearchList
  {search}
  placeholder="Поиск по имени и нику"
  onsearch={find}
  {loaded}
  count={rows.length}
  words={['человек', 'человека', 'человек']}
  filtered={!!search}
  nothing="Никого не найдено"
  empty="Людей пока нет — они заведутся сами, когда бот разберёт переписку"
>
  {#snippet actions()}
    <button class="btn primary" type="button" onclick={() => (adding = true)}>
      <span class="material-symbols-outlined">add</span>
      Человек
    </button>
  {/snippet}

  {#each rows as person (person.id)}
    <PersonRow {person} onpick={() => (opened = person.id)} />
  {/each}

  {#if hasMore}
    <button class="add-more" type="button" onclick={more}>Показать ещё</button>
  {/if}
</SearchList>

{#if adding}
  <AskDialog
    icon="person_add"
    title="Новый человек"
    subtitle="Хотя бы имя, ник или номер учётной записи — иначе карточку потом не найти."
    confirmLabel="Создать"
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <NewPersonFields {draft} onenter={create} />
  </AskDialog>
{/if}

{#if opened}
  <PersonCard
    {ask}
    {say}
    {events}
    personId={opened}
    onclose={() => (opened = null)}
    onchanged={() => refresh(refreshLimit(rows.length))}
  />
{/if}

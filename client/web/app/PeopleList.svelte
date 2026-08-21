<script>
  // Вкладка «HR»: список людей с поиском, страницами и заведением.

  import AskDialog from '$components/AskDialog.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import NewPersonFields from '$components/NewPersonFields.svelte';
  import PersonRow from '$components/PersonRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { pagedList } from '$state/paged_list.svelte.js';

  import PersonCard from './PersonCard.svelte';

  let { ask, say, events, open, onopened, oncompany, onvacancy } = $props();

  const list = pagedList({ ask: (...args) => ask(...args), method: 'hr.list', key: 'hrs' });

  const FORM = NEW_CARD.hr;

  let adding = $state(false);
  let saving = $state(false);
  let draft = $state(FORM.blank());

  // Хоть что-нибудь из трёх: имя, ник или номер учётной записи. Тем же
  // правилом заслоняется и мост.
  const ready = $derived(FORM.named(draft));
  let opened = $state(null);

  // Кого открыть, придя со стороны — из списка непрочитанного над полосой или
  // из карточки вакансии.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  /** Завести человека.
   *
   * Заслон один — назвать хоть чем-нибудь: карточка без имени, ника и номера
   * учётной записи не находится потом ни поиском, ни отправкой. Негодный ник
   * отбивает мост, и его отказ приезжает плашкой.
   */
  async function create() {
    if (!ready) return;
    saving = true;
    const done = await ask('hr.create', { ...draft });
    saving = false;
    // Окно закрываем только по удаче: отказ — это чаще всего опечатка в нике,
    // и набранное человеку ещё пригодится.
    if (done === null) return;
    adding = false;
    draft = FORM.blank();
    say(FORM.done);
    return list.again();
  }

  $effect(() => {
    // Списки меняет не только этот экран: бот заводит людей сам, разбирая
    // переписку, и он же считает непрочитанное.
    // Только про списки: весть о непрочитанном кладётся на каждое сохранённое
    // письмо, и обход в сотню сообщений перечитал бы список сотню раз подряд.
    const deaf = events.on('contacts_lists_changed', () => list.again());
    const settled = list.entered();
    return () => {
      settled();
      deaf();
    };
  });
</script>

<ContactsPanes
  loaded={list.loaded}
  empty={list.rows.length === 0}
  chosen={opened !== null}
  detailEmpty="Выберите HR в списке слева"
  onlistscroll={list.scrolled}
>
  {#snippet toolbar()}
    <SearchBox value={list.search} placeholder={FORM.searchHint} onsearch={list.find} />
    <button
      class="icon-btn cnt-add-btn"
      type="button"
      title="Добавить HR"
      onclick={() => (adding = true)}
    >
      <span class="material-symbols-outlined">{FORM.icon}</span>
    </button>
  {/snippet}

  {#snippet emptyNote()}
    {#if list.search}
      Никого не найдено по запросу «{list.search}».
    {:else}
      HR'ов пока нет.<br />Нажмите кнопку добавления вверху, чтобы создать первого.
    {/if}
  {/snippet}

  {#snippet items()}
    {#each list.rows as person (person.id)}
      <PersonRow
        {person}
        selected={opened === person.id}
        onpick={() => (opened = person.id)}
      />
    {/each}
  {/snippet}

  {#snippet detail()}
    <PersonCard
      {ask}
      {say}
      {events}
      {oncompany}
      {onvacancy}
      personId={opened}
      onclose={() => (opened = null)}
      onchanged={() => list.again()}
    />
  {/snippet}
</ContactsPanes>

{#if adding}
  <AskDialog
    icon={FORM.icon}
    title={FORM.title}
    subtitle={FORM.subtitle}
    confirmLabel="Создать"
    busyLabel={FORM.busyLabel}
    busy={saving}
    {ready}
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <NewPersonFields {draft} />
  </AskDialog>
{/if}

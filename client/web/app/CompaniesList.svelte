<script>
  // Вкладка «Компании»: список слева, карточка выбранной справа.

  import AskDialog from '$components/AskDialog.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import NewCompanyFields from '$components/NewCompanyFields.svelte';
  import CompanyRow from '$components/CompanyRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { pagedList } from '$state/paged_list.svelte.js';

  import CompanyCard from './CompanyCard.svelte';

  let { ask, say, events, open, onopened, onperson, onvacancy } = $props();

  const list = pagedList({
    ask: (...args) => ask(...args),
    method: 'companies.list',
    key: 'companies',
  });

  const FORM = NEW_CARD.company;

  let adding = $state(false);
  let saving = $state(false);
  let draft = $state(FORM.blank());

  const ready = $derived(FORM.named(draft));
  let opened = $state(null);

  // Какую компанию открыть, придя из карточки вакансии.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  async function create() {
    const name = draft.name.trim();
    if (!ready) return;
    saving = true;
    const done = await ask('companies.create', { ...draft, name });
    saving = false;
    // Окно закрываем только по удаче: чаще всего отказ — это занятое имя, и
    // набранное человеку ещё пригодится.
    if (done === null) return;
    adding = false;
    draft = FORM.blank();
    say(FORM.done);
    // Тем же потолком, что и по вести: заведение не повод схлопывать
    // пролистанное.
    return list.again();
  }

  $effect(() => {
    // Списки меняет не только этот экран: бот заводит компании сам, разбирая
    // объявления. Без этой подписки экран показывал бы снимок той минуты,
    // когда его открыли.
    // Перечитываем по вести не страницей, а показанным: иначе занесение в
    // отсев из карточки схлопывало бы пролистанное до первой страницы.
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
  detailEmpty="Выберите компанию в списке слева"
  onlistscroll={list.scrolled}
>
  {#snippet toolbar()}
    <SearchBox
      value={list.search}
      placeholder={FORM.searchHint}
      onsearch={list.find}
    />
    <button
      class="icon-btn cnt-add-btn"
      type="button"
      title="Добавить компанию"
      onclick={() => (adding = true)}
    >
      <span class="material-symbols-outlined">{FORM.icon}</span>
    </button>
  {/snippet}

  {#snippet emptyNote()}
    {#if list.search}
      Ничего не найдено по запросу «{list.search}»
    {:else}
      Компаний пока нет
    {/if}
  {/snippet}

  {#snippet items()}
    {#each list.rows as company (company.id)}
      <CompanyRow
        {company}
        selected={opened === company.id}
        onpick={() => (opened = company.id)}
      />
    {/each}
  {/snippet}

  {#snippet detail()}
    <CompanyCard
      {ask}
      {say}
      {onperson}
      {onvacancy}
      companyId={opened}
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
    <NewCompanyFields {draft} />
  </AskDialog>
{/if}

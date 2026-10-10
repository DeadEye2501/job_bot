<script>
  // Вкладка «Компании»: список слева, карточка выбранной справа.

  import AddButton from '$components/AddButton.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import NewCardDialog from '$components/NewCardDialog.svelte';
  import CompanyRow from '$components/CompanyRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { watchContacts } from '$state/contacts_watch.js';
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

  const newCard = contactAdding({
    list,
    form: FORM,
    // Название подрезается здесь, а не в общем заведении: у человека
    // подрезать нечего — его находят ещё и ником, и номером учётной записи.
    save: (draft) => ask('companies.create', { ...draft, name: draft.name.trim() }),
    say: (text) => say(text),
  });

  // Чья карточка показана справа.
  let opened = $state(null);

  // Какую компанию открыть, придя из карточки вакансии.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  $effect(() => watchContacts(events, list));
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
    <AddButton title="Добавить компанию" icon={FORM.icon} onclick={() => (newCard.adding = true)} />
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

{#if newCard.adding}
  <NewCardDialog
    kind="company"
    draft={newCard.draft}
    busy={newCard.saving}
    ready={newCard.ready}
    onconfirm={() => newCard.create()}
    oncancel={() => (newCard.adding = false)}
  />
{/if}

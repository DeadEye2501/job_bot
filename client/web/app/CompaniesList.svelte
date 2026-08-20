<script>
  // Вкладка «Компании»: список слева, карточка выбранной справа.

  import { untrack } from 'svelte';

  import AskDialog from '$components/AskDialog.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import NewCompanyFields from '$components/NewCompanyFields.svelte';
  import CompanyRow from '$components/CompanyRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { companyNamed } from '$state/companies.js';
  import { pagedList } from '$state/paged_list.svelte.js';

  import CompanyCard from './CompanyCard.svelte';

  let { ask, say, events, open, onopened, onperson, onvacancy } = $props();

  const list = pagedList({
    ask: (...args) => ask(...args),
    method: 'companies.list',
    key: 'companies',
  });

  let adding = $state(false);
  let draft = $state({ name: '', website: '', aliases: '', notes: '' });

  const ready = $derived(companyNamed(draft));
  let opened = $state(null);

  // Какую компанию открыть, придя из карточки вакансии. Отметка гасится сразу:
  // вкладку открывают и просто так, и заново открытая карточка компании,
  // которую уже закрыли, читалась бы как поломка.
  $effect(() => {
    if (!open) return;
    opened = open.id;
    onopened();
  });

  async function create() {
    const name = draft.name.trim();
    if (!ready) return;
    const done = await ask('companies.create', { ...draft, name });
    // Окно закрываем только по удаче: чаще всего отказ — это занятое имя, и
    // набранное человеку ещё пригодится.
    if (done === null) return;
    adding = false;
    draft = { name: '', website: '', aliases: '', notes: '' };
    say('Компания заведена');
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
    const settled = list.mounted();
    // Первое чтение — вне слежения: строку поиска читает `refresh`, и следящий
    // эффект перезаводился бы на каждом набранном знаке.
    untrack(() => list.refresh());
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
      placeholder="Поиск по названию, алиасу, домену..."
      onsearch={list.find}
    />
    <button
      class="cnt-add-btn"
      type="button"
      title="Добавить компанию"
      onclick={() => (adding = true)}
    >
      <span class="material-symbols-outlined">add_business</span>
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
    icon="domain_add"
    title="Новая компания"
    subtitle="Название обязательно, остальное можно дописать потом."
    confirmLabel="Создать"
    {ready}
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <NewCompanyFields {draft} />
  </AskDialog>
{/if}

<script>
  // Вкладка «Компании»: общая вкладка контактов со строкой и карточкой компании.

  import CompanyRow from '$components/CompanyRow.svelte';
  import { pagedList } from '$state/paged_list.svelte.js';

  import CompanyCard from './CompanyCard.svelte';
  import ContactsTab from './ContactsTab.svelte';

  let { ask, say, events, open, onopened, onperson, onvacancy } = $props();

  const list = pagedList({
    ask: (...args) => ask(...args),
    method: 'companies.list',
    key: 'companies',
  });

  const words = {
    add: 'Добавить компанию',
    pick: 'Выберите компанию в списке слева',
    none: 'Компаний пока нет',
  };
</script>

<!-- Название подрезается здесь, а не в общем заведении: у человека подрезать
     нечего — его находят ещё и ником, и номером учётной записи. -->
<ContactsTab
  kind="company"
  {words}
  {list}
  save={(draft) => ask('companies.create', { ...draft, name: draft.name.trim() })}
  {say}
  {events}
  {open}
  {onopened}
>
  {#snippet row(company, at)}
    <CompanyRow {company} selected={at.selected} onpick={at.pick} />
  {/snippet}

  {#snippet pane(companyId, close)}
    <CompanyCard
      {ask}
      {say}
      {onperson}
      {onvacancy}
      {companyId}
      onclose={close}
      onchanged={() => list.again()}
    />
  {/snippet}
</ContactsTab>

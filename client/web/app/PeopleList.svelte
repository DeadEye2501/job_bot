<script>
  // Вкладка «HR»: общая вкладка контактов со строкой и карточкой человека.

  import PersonRow from '$components/PersonRow.svelte';
  import { pagedList } from '$state/paged_list.svelte.js';

  import ContactsTab from './ContactsTab.svelte';
  import PersonCard from './PersonCard.svelte';

  let { ask, say, events, open, onopened, oncompany, onvacancy } = $props();

  const list = pagedList({ ask: (...args) => ask(...args), method: 'hr.list', key: 'hrs' });

  const words = {
    add: 'Добавить HR',
    pick: 'Выберите HR в списке слева',
    none: "HR'ов пока нет",
  };
</script>

<!-- Негодный ник отбивает мост, и его отказ приезжает плашкой — потому здесь
     и не проверяется ничего сверх общего заслона. -->
<ContactsTab
  kind="hr"
  {words}
  {list}
  save={(draft) => ask('hr.create', { ...draft })}
  {say}
  {events}
  {open}
  {onopened}
>
  {#snippet row(person, at)}
    <PersonRow {person} selected={at.selected} onpick={at.pick} />
  {/snippet}

  {#snippet pane(personId, close)}
    <PersonCard
      {ask}
      {say}
      {events}
      {oncompany}
      {onvacancy}
      {personId}
      onclose={close}
      onchanged={() => list.again()}
    />
  {/snippet}
</ContactsTab>

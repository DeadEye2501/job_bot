<script>
  // Вкладка «HR»: список людей с поиском, страницами и заведением.

  import ContactsPanes from '$components/ContactsPanes.svelte';
  import NewCardDialog from '$components/NewCardDialog.svelte';
  import PersonRow from '$components/PersonRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { watchContacts } from '$state/contacts_watch.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { pagedList } from '$state/paged_list.svelte.js';

  import PersonCard from './PersonCard.svelte';

  let { ask, say, events, open, onopened, oncompany, onvacancy } = $props();

  const list = pagedList({ ask: (...args) => ask(...args), method: 'hr.list', key: 'hrs' });

  const FORM = NEW_CARD.hr;

  // Негодный ник отбивает мост, и его отказ приезжает плашкой — потому здесь
  // и не проверяется ничего сверх общего заслона.
  const newCard = contactAdding({
    list,
    form: FORM,
    save: (draft) => ask('hr.create', { ...draft }),
    say: (text) => say(text),
  });

  // Чья карточка показана справа.
  let opened = $state(null);

  // Кого открыть, придя со стороны — из списка непрочитанного над полосой или
  // из карточки вакансии.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  // Только про списки: весть о непрочитанном кладётся на каждое сохранённое
  // письмо, и обход в сотню сообщений перечитал бы список сотню раз подряд.
  $effect(() => watchContacts(events, list));
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
      onclick={() => (newCard.adding = true)}
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

{#if newCard.adding}
  <NewCardDialog
    kind="hr"
    draft={newCard.draft}
    busy={newCard.saving}
    ready={newCard.ready}
    onconfirm={() => newCard.create()}
    oncancel={() => (newCard.adding = false)}
  />
{/if}

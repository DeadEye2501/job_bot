<script>
  // Вкладка контактов — людей или компаний: список страницами слева, карточка
  // выбранного справа, поиск и заведение сверху.
  //
  // Одной сборкой на оба рода: смотрят на них одинаково, а различия приходят
  // доводами — слова, список, запись заведённого, строка и карточка
  // фрагментами. Список собирает сама вкладка рода: имя метода моста должно
  // стоять литералом там, где его видит шов имён.
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import NewCardDialog from '$components/NewCardDialog.svelte';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { watchContacts } from '$state/contacts_watch.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';

  let { kind, words, list, save, say, events, open, onopened, row, pane } = $props();

  const form = NEW_CARD[kind];

  const newCard = contactAdding({ list, form, save, say: (text) => say(text) });

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
  search={list.search}
  searchHint={form.searchHint}
  addTitle={words.add}
  addIcon={form.icon}
  none={words.none}
  detailEmpty={words.pick}
  onsearch={list.find}
  onadd={() => (newCard.adding = true)}
  onlistscroll={list.scrolled}
>
  {#snippet items()}
    {#each list.rows as item (item.id)}
      {@render row(item, { selected: opened === item.id, pick: () => (opened = item.id) })}
    {/each}
  {/snippet}

  {#snippet detail()}
    {@render pane(opened, () => (opened = null))}
  {/snippet}
</ContactsPanes>

{#if newCard.adding}
  <NewCardDialog
    {kind}
    draft={newCard.draft}
    busy={newCard.saving}
    ready={newCard.ready}
    onconfirm={() => newCard.create()}
    oncancel={() => (newCard.adding = false)}
  />
{/if}

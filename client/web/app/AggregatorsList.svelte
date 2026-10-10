<script>
  // Вкладка «Агрегаторы»: список слева, карточка выбранного справа — так же,
  // как у каналов: это тоже источники вакансий, и смотрят на них так же.

  import { call } from '$api/bridge.js';
  import AddButton from '$components/AddButton.svelte';
  import AddressDialog from '$components/AddressDialog.svelte';
  import AggregatorRow from '$components/AggregatorRow.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import RowToggle from '$components/RowToggle.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { living } from '$state/alive.js';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { watchContacts } from '$state/contacts_watch.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { detailScrolled } from '$state/paging.js';
  import { round } from '$state/round.svelte.js';
  import { sourceList } from '$state/source_list.svelte.js';
  import { masterToggle } from '$state/sources.js';

  import AggregatorCard from './AggregatorCard.svelte';

  let { ask, say, lockedTip, events, open, onopened, onvacancy } = $props();

  let opened = $state(null);
  let card = $state(null);

  const list = sourceList({
    alive: living(),
    key: 'aggregators',
    read: (search) => ask('aggregators.list', { search }),
    setActive: (row, on) => ask('aggregators.set_active', { aggregator_id: row.id, is_active: on }),
    setAll: (on) => ask('aggregators.set_all_active', { is_active: on }),
  });

  // Чем заперты действия агента — словами моста о водителе и браузере.
  const lock = $derived(list.answer?.lock ?? null);
  const master = $derived(masterToggle(list.enabled, 'агрегаторов'));

  // Какой агрегатор открыть, придя со стороны — из таблицы источников в статистике.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  // Заведённый агрегатор сразу открывается справа: без входа его не включить,
  // и войти человеку предстоит из его карточки.
  const newAggregator = contactAdding({
    list: {
      again: (done) => {
        opened = done.aggregator.id;
        return list.again();
      },
    },
    form: NEW_CARD.aggregator,
    save: (draft) => call('aggregators.create', { address: draft.trim() }),
    say: (text) => say(text),
  });

  // Вход и обход кончаются вестью о конце прогона: отметка входа, время обхода
  // и счёт вакансий меняются тогда, а не по нажатию.
  $effect(() => round.onFinish(list.again));

  $effect(() => watchContacts(events, list));
  // Потерянные вести — конец прогона в их числе — заменяет перечитывание.
  $effect(() => events.on('missed', list.again));
</script>

<ContactsPanes
  loaded={list.loaded}
  empty={list.rows.length === 0}
  chosen={opened !== null}
  detailEmpty="Выберите агрегатор в списке"
  ondetailscroll={(event) => detailScrolled(event, card)}
>
  {#snippet toolbar()}
    <SearchBox value={list.search} placeholder="Поиск агрегатора..." onsearch={list.find} />
    <AddButton title="Добавить агрегатор" onclick={() => (newAggregator.adding = true)} />
    <RowToggle checked={master.checked} title={master.title} ontoggle={list.toggleAll} />
  {/snippet}

  {#snippet emptyNote()}
    Ничего не найдено по запросу «{list.search}»
  {/snippet}

  {#snippet items()}
    {#each list.rows as row (row.id)}
      <AggregatorRow
        {row}
        enabled={list.enabled}
        selected={opened === row.id}
        onpick={() => (opened = row.id)}
        ontoggle={(on) => list.toggle(row, on)}
      />
    {/each}
  {/snippet}

  {#snippet detail()}
    <AggregatorCard
      bind:this={card}
      {ask}
      {say}
      {lockedTip}
      {lock}
      {events}
      {onvacancy}
      aggregatorId={opened}
      onclose={() => (opened = null)}
      onchanged={list.again}
    />
  {/snippet}
</ContactsPanes>

{#if newAggregator.adding}
  <AddressDialog
    kind="aggregator"
    value={newAggregator.draft}
    trouble={newAggregator.trouble}
    saving={newAggregator.saving}
    ready={newAggregator.ready}
    oninput={(text) => (newAggregator.draft = text)}
    onadd={() => newAggregator.create()}
    onclose={() => (newAggregator.adding = false)}
  />
{/if}

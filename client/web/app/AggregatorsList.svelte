<script>
  // Вкладка «Агрегаторы»: общая вкладка источников со строкой и карточкой
  // агрегатора. Заведённый агрегатор сразу открывается справа: без входа его
  // не включить, и войти человеку предстоит из его карточки.

  import { call } from '$api/bridge.js';
  import AggregatorRow from '$components/AggregatorRow.svelte';
  import { AGGREGATORS_TAB } from '$state/aggregators.js';

  import AggregatorCard from './AggregatorCard.svelte';
  import SourcesTab from './SourcesTab.svelte';

  let { ask, say, lockedTip, events, open, onopened, onchosen, onvacancy } = $props();

  const source = {
    key: 'aggregators',
    read: (search) => ask('aggregators.list', { search }),
    setActive: (row, on) => ask('aggregators.set_active', { aggregator_id: row.id, is_active: on }),
    setAll: (on) => ask('aggregators.set_all_active', { is_active: on }),
    save: (draft) => call('aggregators.create', { address: draft.trim() }),
  };
</script>

<SourcesTab
  kind="aggregator"
  words={AGGREGATORS_TAB}
  {source}
  openCreated={(done) => done.aggregator.id}
  rereadOnRound
  {say}
  {events}
  {open}
  {onopened}
  {onchosen}
>
  {#snippet row(item, at)}
    <AggregatorRow
      row={item}
      enabled={at.enabled}
      selected={at.selected}
      onpick={at.pick}
      ontoggle={at.toggle}
    />
  {/snippet}

  {#snippet pane(shown)}
    <!-- `lock` — чем заперты действия агента: слова моста о водителе и браузере. -->
    <AggregatorCard
      bind:this={shown.getCard, shown.setCard}
      {ask}
      {say}
      {lockedTip}
      lock={shown.list.answer?.lock ?? null}
      {events}
      {onvacancy}
      aggregatorId={shown.opened}
      onclose={shown.close}
      onchanged={shown.list.again}
    />
  {/snippet}
</SourcesTab>

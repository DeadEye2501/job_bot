<script>
  // Раздел «Контакты»: вкладки списков.
  //
  // Каналы и чёрный список — разные предметы, но обвязка у них одна: поиск,
  // список, заведение, удаление. Общее живёт компонентами, своё — в каждом.
  //
  // Он же и переводит с вкладки на вкладку: из карточки компании уходят к её
  // человеку, из карточки человека — к его компании, и знать друг о друге
  // спискам для этого не нужно.

  import TopTabs from '$components/TopTabs.svelte';
  import { markOf } from '$state/open_mark.js';
  import { CONTACTS_TABS } from '$state/sections.js';

  import AggregatorsList from './AggregatorsList.svelte';
  import BlacklistList from './BlacklistList.svelte';
  import ChannelsList from './ChannelsList.svelte';
  import CompaniesList from './CompaniesList.svelte';
  import PeopleList from './PeopleList.svelte';

  // Вкладку и открытую карточку держит оболочка (`sectionMemory`).
  let { ask, say, lockedTip, events, openCard, onopened, onvacancy, tab, ontab, onchosen } =
    $props();

  let mark = $state(null);

  // Пришли со стороны — открываем ту вкладку, где названная карточка живёт:
  // показывает её она, а не та, на которой раздел закрыли в прошлый раз.
  // Отметку снаружи гасим сразу: раздел открывают и просто так.
  $effect(() => {
    if (!openCard) return;
    go(openCard);
    onopened();
  });

  function go(one) {
    mark = one;
    ontab(one.tab);
  }

  // Отметка достаётся только своей вкладке: чужой номер соседний список принял
  // бы за свой и открыл бы карточку с тем же номером.
  const mine = (key) => (mark?.tab === key ? mark : null);

  // Открытая карточка уходит наружу той же отметкой, какой приходит со стороны:
  // вернувшись в раздел, её отдают обратно, и открывает её тот же путь.
  const chose = (key) => (id) => onchosen(markOf(id, { tab: key }));
</script>

<TopTabs tabs={CONTACTS_TABS} active={tab} onpick={ontab} />

<div class="screen-body" class:flush={tab !== 'blacklist'}>
  {#if tab === 'aggregators'}
    <AggregatorsList
      {ask}
      {say}
      {lockedTip}
      {events}
      {onvacancy}
      open={mine('aggregators')}
      onopened={() => (mark = null)}
      onchosen={chose('aggregators')}
    />
  {:else if tab === 'channels'}
    <ChannelsList
      {ask}
      {say}
      {lockedTip}
      {events}
      {onvacancy}
      open={mine('channels')}
      onopened={() => (mark = null)}
      onchosen={chose('channels')}
    />
  {:else if tab === 'companies'}
    <CompaniesList
      {ask}
      {say}
      {events}
      {onvacancy}
      open={mine('companies')}
      onopened={() => (mark = null)}
      onchosen={chose('companies')}
      onperson={(id) => go({ tab: 'people', id })}
    />
  {:else if tab === 'people'}
    <PeopleList
      {ask}
      {say}
      {events}
      {onvacancy}
      open={mine('people')}
      onopened={() => (mark = null)}
      onchosen={chose('people')}
      oncompany={(id) => go({ tab: 'companies', id })}
    />
  {:else}
    <BlacklistList {ask} {say} {events} />
  {/if}
</div>

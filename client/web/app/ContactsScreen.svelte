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
  import { CONTACTS_TABS } from '$state/sections.js';

  import BlacklistList from './BlacklistList.svelte';
  import ChannelsList from './ChannelsList.svelte';
  import CompaniesList from './CompaniesList.svelte';
  import PeopleList from './PeopleList.svelte';

  let { ask, say, lockedTip, events, openCard, onopened, onvacancy } = $props();

  let tab = $state(CONTACTS_TABS[0].key);
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
    tab = one.tab;
  }

  // Отметка достаётся только своей вкладке: чужой номер соседний список принял
  // бы за свой и открыл бы карточку с тем же номером.
  const mine = (key) => (mark?.tab === key ? mark : null);
</script>

<TopTabs tabs={CONTACTS_TABS} active={tab} onpick={(key) => (tab = key)} />

<div class="screen-body" class:flush={tab !== 'blacklist'}>
  {#if tab === 'channels'}
    <ChannelsList {ask} {say} {lockedTip} {events} {onvacancy} />
  {:else if tab === 'companies'}
    <CompaniesList
      {ask}
      {say}
      {events}
      {onvacancy}
      open={mine('companies')}
      onopened={() => (mark = null)}
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
      oncompany={(id) => go({ tab: 'companies', id })}
    />
  {:else}
    <BlacklistList {ask} {say} {events} />
  {/if}
</div>

<script>
  // Раздел «Контакты»: вкладки списков.
  //
  // Каналы и чёрный список — разные предметы, но обвязка у них одна: поиск,
  // список, заведение, удаление. Общее живёт компонентами, своё — в каждом.

  import TopTabs from '$components/TopTabs.svelte';
  import { CONTACTS_TABS } from '$state/sections.js';

  import BlacklistList from './BlacklistList.svelte';
  import ChannelsList from './ChannelsList.svelte';
  import CompaniesList from './CompaniesList.svelte';
  import PeopleList from './PeopleList.svelte';

  let { ask, say, lockedTip, events, openCard, onopened } = $props();

  let tab = $state(CONTACTS_TABS[0].key);

  // Пришли со стороны — открываем ту вкладку, где названная карточка живёт:
  // показывает её она, а не та, на которой раздел закрыли в прошлый раз.
  $effect(() => {
    if (openCard) tab = openCard.tab;
  });

  // Отметка достаётся только своей вкладке: чужой номер соседний список принял
  // бы за свой и открыл бы карточку с тем же номером.
  const mine = (key) => (openCard?.tab === key ? openCard : null);
</script>

<TopTabs tabs={CONTACTS_TABS} active={tab} onpick={(key) => (tab = key)} />

<div class="screen-body">
  {#if tab === 'channels'}
    <ChannelsList {ask} {say} {lockedTip} {events} />
  {:else if tab === 'companies'}
    <CompaniesList {ask} {say} {events} open={mine('companies')} {onopened} />
  {:else if tab === 'people'}
    <PeopleList {ask} {say} {events} open={mine('people')} {onopened} />
  {:else}
    <BlacklistList {ask} {say} {events} />
  {/if}
</div>

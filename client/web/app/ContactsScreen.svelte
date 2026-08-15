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

  let { ask, say, lockedTip, events, openPerson, onopened } = $props();

  let tab = $state(CONTACTS_TABS[0].key);

  // Пришли из списка непрочитанного — открываем ту вкладку, где человек живёт:
  // выбранного показывает она, а не та, на которой раздел закрыли в прошлый раз.
  $effect(() => {
    if (openPerson) tab = 'people';
  });
</script>

<TopTabs tabs={CONTACTS_TABS} active={tab} onpick={(key) => (tab = key)} />

<div class="screen-body">
  {#if tab === 'channels'}
    <ChannelsList {ask} {say} {lockedTip} {events} />
  {:else if tab === 'companies'}
    <CompaniesList {ask} {say} {events} />
  {:else if tab === 'people'}
    <PeopleList {ask} {say} {events} {openPerson} {onopened} />
  {:else}
    <BlacklistList {ask} {say} {events} />
  {/if}
</div>

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

  let { ask, say, events } = $props();

  let tab = $state(CONTACTS_TABS[0].key);
</script>

<TopTabs tabs={CONTACTS_TABS} active={tab} onpick={(key) => (tab = key)} />

<div class="screen-body">
  {#if tab === 'channels'}
    <ChannelsList {ask} {say} {events} />
  {:else if tab === 'companies'}
    <CompaniesList {ask} {say} {events} />
  {:else if tab === 'people'}
    <PeopleList {ask} {say} {events} />
  {:else}
    <BlacklistList {ask} {say} {events} />
  {/if}
</div>

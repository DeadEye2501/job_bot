<script>
  // Вкладка «Каналы»: список слева, карточка выбранного справа.

  import { call } from '$api/bridge.js';
  import AddButton from '$components/AddButton.svelte';
  import AddressDialog from '$components/AddressDialog.svelte';
  import ChannelRow from '$components/ChannelRow.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import RowToggle from '$components/RowToggle.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { living } from '$state/alive.js';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { watchContacts } from '$state/contacts_watch.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { detailScrolled } from '$state/paging.js';
  import { sourceList } from '$state/source_list.svelte.js';
  import { masterToggle } from '$state/sources.js';

  import ChannelCard from './ChannelCard.svelte';

  let { ask, say, lockedTip, events, open, onopened, onvacancy } = $props();

  let opened = $state(null);
  let card = $state(null);

  // Каналы приходят разом, без страниц: их десятки, а не тысячи.
  const list = sourceList({
    alive: living(),
    key: 'channels',
    read: (search) => ask('channels.list', { search }),
    setActive: (channel, on) => ask('channels.set_active', { channel_id: channel.id, is_active: on }),
    setAll: (on) => ask('channels.set_all_active', { is_active: on }),
  });

  const master = $derived(masterToggle(list.enabled, 'каналов'));

  // Какой канал открыть, придя со стороны — из воронки каналов в статистике.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  // Канал заводят мостом напрямую, а не общей обёрткой: та показывает отказ
  // плашкой и отдаёт пустоту, и слова моста — какое имя не нашлось и какие
  // написания он понимает — гасли бы в углу, пока человек смотрит в поле.
  const newChannel = contactAdding({
    list,
    form: NEW_CARD.channel,
    save: (draft) => call('channels.create', { input: draft.trim() }),
    say: (text) => say(text),
  });

  // Списки меняет не только этот экран: бот заносит каналы в отсев сам,
  // разбирая объявления.
  $effect(() => watchContacts(events, list));
</script>

<ContactsPanes
  loaded={list.loaded}
  empty={list.rows.length === 0}
  chosen={opened !== null}
  detailEmpty="Выберите канал в списке"
  ondetailscroll={(event) => detailScrolled(event, card)}
>
  {#snippet toolbar()}
    <SearchBox value={list.search} placeholder="Поиск канала..." onsearch={list.find} />
    <AddButton title="Добавить канал" onclick={() => (newChannel.adding = true)} />
    <!-- Общий выключатель поверх строк: выключенный, гасит обход всех каналов,
         но положения строк хранит. -->
    <RowToggle checked={master.checked} title={master.title} ontoggle={list.toggleAll} />
  {/snippet}

  {#snippet emptyNote()}
    {#if list.search}
      Ничего не найдено по запросу «{list.search}»
    {:else}
      Каналов пока нет
    {/if}
  {/snippet}

  {#snippet items()}
    {#each list.rows as channel (channel.id)}
      <ChannelRow
        {channel}
        enabled={list.enabled}
        selected={opened === channel.id}
        onpick={() => (opened = channel.id)}
        ontoggle={(on) => list.toggle(channel, on)}
      />
    {/each}
  {/snippet}

  {#snippet detail()}
    <ChannelCard
      bind:this={card}
      {ask}
      {say}
      {lockedTip}
      {events}
      {onvacancy}
      channelId={opened}
      onclose={() => (opened = null)}
      onchanged={list.again}
    />
  {/snippet}
</ContactsPanes>

{#if newChannel.adding}
  <AddressDialog
    kind="channel"
    value={newChannel.draft}
    trouble={newChannel.trouble}
    saving={newChannel.saving}
    ready={newChannel.ready}
    oninput={(text) => (newChannel.draft = text)}
    onadd={() => newChannel.create()}
    onclose={() => (newChannel.adding = false)}
  />
{/if}

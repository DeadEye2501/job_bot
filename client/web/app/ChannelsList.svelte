<script>
  // Вкладка «Каналы»: список с поиском, переключением опроса и заведением.

  import ChannelRow from '$components/ChannelRow.svelte';

  import ChannelCard from './ChannelCard.svelte';
  import AskDialog from '$components/AskDialog.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import SearchList from '$components/SearchList.svelte';
  import { fresher } from '$state/contacts.js';

  let { ask, say, events } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let search = $state('');
  let adding = $state(false);
  let draft = $state('');
  let leaving = $state(null);
  let opened = $state(null);

  let asked = 0;
  let alive = true;

  /** Перечитать список.
   *
   * Каждому вопросу свой порядковый знак, и мост возвращает его эхом: человек
   * набирает поиск посимвольно, ответы приходят вразнобой, и лёгший поверх
   * свежего старый показал бы строки, которых он уже не ищет.
   */
  async function refresh() {
    asked += 1;
    const mine = asked;
    const now = await ask('channels.list', { search, epoch: mine });
    if (now === null || !alive || !fresher(now.epoch, asked)) return;
    rows = now.channels;
    loaded = true;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  async function toggle(channel, on) {
    await ask('channels.set_active', { channel_id: channel.id, is_active: on });
    return refresh();
  }

  async function toggleAll(on) {
    await ask('channels.set_all_active', { is_active: on });
    return refresh();
  }

  async function create() {
    const value = draft.trim();
    if (!value) return;
    const done = await ask('channels.create', { input: value });
    // Окно закрываем только по удаче: отказ — это чаще всего опечатка в нике,
    // и набранное человеку ещё пригодится.
    if (done === null) return;
    adding = false;
    draft = '';
    say(done.created ? `Канал добавлен: @${done.username}` : `Канал @${done.username} уже был заведён`);
    return refresh();
  }

  async function drop(channel) {
    leaving = null;
    const done = await ask('channels.delete', channel.id);
    if (done === null) return;
    return refresh();
  }

  $effect(() => {
    alive = true;
    // Списки меняет не только этот экран: бот заносит людей и компании в отсев
    // сам, разбирая переписку. Без этой подписки экран показывал бы снимок той
    // минуты, когда его открыли.
    const deaf = events.on('contacts_lists_changed', refresh);
    refresh();
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

<SearchList
  {search}
  placeholder="Поиск по каналам"
  onsearch={find}
  {loaded}
  count={rows.length}
  words={['канал', 'канала', 'каналов']}
  filtered={!!search}
  nothing="Ничего не найдено"
  empty="Каналов пока нет — добавьте первый"
>
  {#snippet actions()}
    <button class="btn" type="button" onclick={() => toggleAll(true)}>Включить все</button>
    <button class="btn" type="button" onclick={() => toggleAll(false)}>Выключить все</button>
    <button class="btn primary" type="button" onclick={() => (adding = true)}>
      <span class="material-symbols-outlined">add</span>
      Канал
    </button>
  {/snippet}

  {#each rows as channel (channel.id)}
    <ChannelRow
      {channel}
      onpick={() => (opened = channel.id)}
      ontoggle={(on) => toggle(channel, on)}
      onremove={() => (leaving = channel)}
    />
  {/each}
</SearchList>

{#if adding}
  <AskDialog
    icon="add"
    title="Новый канал"
    subtitle="Ник канала или ссылка на него."
    confirmLabel="Добавить"
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="input"
      autofocus
      placeholder="@python_jobs"
      bind:value={draft}
      onkeydown={(event) => event.key === 'Enter' && create()}
    />
  </AskDialog>
{/if}

{#if opened}
  <ChannelCard
    {ask}
    {say}
    channelId={opened}
    onclose={() => (opened = null)}
    onchanged={refresh}
  />
{/if}

{#if leaving}
  <ConfirmDialog
    message={`Удалить канал «${leaving.title || leaving.username}»?\n\nВакансии, уже собранные с него, останутся. Откатить удаление нельзя.`}
    confirmLabel="Удалить"
    onconfirm={() => drop(leaving)}
    oncancel={() => (leaving = null)}
  />
{/if}

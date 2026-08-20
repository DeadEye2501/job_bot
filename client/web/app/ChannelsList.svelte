<script>
  // Вкладка «Каналы»: список слева, карточка выбранного справа.

  import { untrack } from 'svelte';

  import AddChannelDialog from '$components/AddChannelDialog.svelte';
  import ChannelRow from '$components/ChannelRow.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { attempts } from '$state/attempts.js';
  import { channelsToggle } from '$state/channels.js';
  import { nearBottom } from '$state/paging.js';

  import ChannelCard from './ChannelCard.svelte';

  let { ask, say, lockedTip, events, open, onopened, onvacancy } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let search = $state('');
  let adding = $state(false);
  let draft = $state('');
  let saving = $state(false);
  let trouble = $state('');
  let opened = $state(null);
  let card = $state(null);

  const tries = attempts();
  let alive = true;

  const master = $derived(channelsToggle(rows));

  // Какой канал открыть, придя со стороны — из воронки каналов в статистике.
  // Отметка гасится сразу: вкладку открывают и просто так, и заново открытая
  // карточка канала, который уже закрыли, читалась бы как поломка.
  $effect(() => {
    if (!open) return;
    opened = open.id;
    onopened();
  });

  /** Перечитать список.
   *
   * Каналы приходят разом, без страниц: их десятки, а не тысячи. Счёт попыток
   * всё равно свой — человек набирает поиск посимвольно, ответы возвращаются
   * вразнобой, и лёгший поверх свежего старый показал бы строки, которых он уже
   * не ищет.
   */
  async function refresh() {
    const mine = tries.next();
    const now = await ask('channels.list', { search });
    if (now === null || !alive || tries.stale(mine)) return;
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

  /** Завести канал по нику или ссылке.
   *
   * Отказ остаётся в окне, а не уезжает общей плашкой: чаще всего это опечатка
   * в нике, и объясняют её там же, где его набирали.
   */
  async function create() {
    const value = draft.trim();
    if (!value || saving) return;
    saving = true;
    trouble = '';
    const done = await ask('channels.create', { input: value });
    saving = false;
    if (done === null) return (trouble = 'Не удалось добавить канал');
    adding = false;
    draft = '';
    say(done.created ? `Канал добавлен: @${done.username}` : `Канал @${done.username} уже был заведён`);
    return refresh();
  }

  /** Дочитать вакансии открытого канала: прокручивается панель целиком, и знает
   *  об этой прокрутке она, а не сама карточка. */
  function paneScrolled(event) {
    if (card !== null && nearBottom(event.currentTarget)) card.more();
  }

  $effect(() => {
    alive = true;
    // Списки меняет не только этот экран: бот заносит каналы в отсев сам,
    // разбирая объявления. Без этой подписки экран показывал бы снимок той
    // минуты, когда его открыли.
    const deaf = events.on('contacts_lists_changed', refresh);
    // Первое чтение — вне слежения: строку поиска `refresh` читает, и следящий
    // эффект перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

<ContactsPanes
  {loaded}
  empty={rows.length === 0}
  chosen={opened !== null}
  detailEmpty="Выберите канал в списке"
  ondetailscroll={paneScrolled}
>
  {#snippet toolbar()}
    <SearchBox value={search} placeholder="Поиск канала..." onsearch={find} />
    <button
      class="cnt-add-btn"
      type="button"
      title="Добавить канал"
      onclick={() => (adding = true)}
    >
      <span class="material-symbols-outlined">add_circle</span>
    </button>
    <!-- Один переключатель на весь список: он же и показывает, все ли каналы
         опрашиваются. -->
    <input
      type="checkbox"
      class="toggle compact"
      checked={master.checked}
      disabled={master.disabled}
      title={master.title}
      onchange={(event) => toggleAll(event.currentTarget.checked)}
    />
  {/snippet}

  {#snippet emptyNote()}
    {#if search}
      Ничего не найдено по запросу «{search}»
    {:else}
      Каналов пока нет
    {/if}
  {/snippet}

  {#snippet items()}
    {#each rows as channel (channel.id)}
      <ChannelRow
        {channel}
        selected={opened === channel.id}
        onpick={() => (opened = channel.id)}
        ontoggle={(on) => toggle(channel, on)}
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
      onchanged={refresh}
    />
  {/snippet}
</ContactsPanes>

{#if adding}
  <AddChannelDialog
    value={draft}
    {trouble}
    {saving}
    oninput={(text) => (draft = text)}
    onadd={create}
    onclose={() => {
      adding = false;
      trouble = '';
    }}
  />
{/if}

<script>
  // Вкладка «Каналы»: список слева, карточка выбранного справа.

  import { untrack } from 'svelte';

  import { call } from '$api/bridge.js';
  import AddChannelDialog from '$components/AddChannelDialog.svelte';
  import ChannelRow from '$components/ChannelRow.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import RowToggle from '$components/RowToggle.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { living } from '$state/alive.js';
  import { channelsToggle } from '$state/channels.js';
  import { freshAnswer } from '$state/fresh.js';
  import { takeOpened } from '$state/open_mark.js';
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

  const alive = living();
  const fresh = freshAnswer(() => alive.now);

  const master = $derived(channelsToggle(rows));

  // Какой канал открыть, придя со стороны — из воронки каналов в статистике.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  /** Перечитать список.
   *
   * Каналы приходят разом, без страниц: их десятки, а не тысячи. Счёт попыток
   * всё равно свой — человек набирает поиск посимвольно, ответы возвращаются
   * вразнобой, и лёгший поверх свежего старый показал бы строки, которых он уже
   * не ищет.
   */
  async function refresh() {
    const now = await fresh(() => ask('channels.list', { search }));
    if (now === null) return;
    rows = now.channels;
    loaded = true;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  /** Включить опрос канала или снять его.
   *
   * Отвечает, легло ли: строка держит положение переключателя у себя, и без
   * ответа отказ остался бы невидимым — человек считал бы канал выключенным,
   * а обход читал бы его дальше.
   */
  async function toggle(channel, on) {
    const done = await ask('channels.set_active', { channel_id: channel.id, is_active: on });
    await refresh();
    return done !== null;
  }

  /** Включить опрос у всех каналов разом или снять его.
   *
   * Отвечает, легло ли: общий переключатель держит положение у себя, как и
   * строчные, и без ответа отказ остался бы невидимым.
   */
  async function toggleAll(on) {
    const done = await ask('channels.set_all_active', { is_active: on });
    await refresh();
    return done !== null;
  }

  /** Завести канал по нику или ссылке.
   *
   * Отказ остаётся в окне, а не уезжает общей плашкой: чаще всего это опечатка
   * в нике, и объясняют её там же, где его набирали.
   *
   * Зовём мост напрямую, как соседи с предметным отказом: общая обёртка
   * показывает плашку и отдаёт пустоту, и слова моста — какое имя не нашлось и
   * какие написания он понимает — гасли в углу, пока человек смотрел в поле.
   */
  async function create() {
    const value = draft.trim();
    if (!value || saving) return;
    saving = true;
    trouble = '';
    let done;
    try {
      done = await call('channels.create', { input: value });
    } catch (refusal) {
      if (!alive.now) return;
      saving = false;
      trouble = refusal.message;
      return;
    }
    if (!alive.now) return;
    saving = false;
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
    const settled = alive.mounted();
    // Списки меняет не только этот экран: бот заносит каналы в отсев сам,
    // разбирая объявления. Без этой подписки экран показывал бы снимок той
    // минуты, когда его открыли.
    const deaf = events.on('contacts_lists_changed', refresh);
    // Первое чтение — вне слежения: строку поиска `refresh` читает, и следящий
    // эффект перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      settled();
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
      class="icon-btn cnt-add-btn"
      type="button"
      title="Добавить канал"
      onclick={() => (adding = true)}
    >
      <span class="material-symbols-outlined">add_circle</span>
    </button>
    <!-- Один переключатель на весь список: он же и показывает, все ли каналы
         опрашиваются. -->
    <RowToggle
      checked={master.checked}
      disabled={master.disabled}
      title={master.title}
      ontoggle={toggleAll}
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

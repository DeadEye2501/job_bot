<script>
  // Вкладка «Чёрный список»: строки отсева с отбором по роду и поиском.
  //
  // Отбор идёт у себя, а не на мосту: строк мало, мост шлёт их разом, и
  // спрашивать его на каждый набранный знак значило бы ждать сеть ради того,
  // что уже лежит в памяти.

  import AskDialog from '$components/AskDialog.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import SearchList from '$components/SearchList.svelte';
  import { BLACKLIST_KINDS, blacklistShown } from '$state/contacts.js';

  let { ask, say, events } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let kind = $state('');
  let search = $state('');
  let adding = $state(false);
  let draft = $state({ kind: 'hr', value: '', reason: '' });
  let leaving = $state(null);

  const shown = $derived(blacklistShown(rows, { kind, search }));

  let alive = true;

  async function refresh() {
    const now = await ask('blacklist.list');
    if (now === null || !alive) return;
    rows = now.items;
    loaded = true;
  }

  async function create() {
    const value = draft.value.trim();
    if (!value) return;
    const done = await ask('blacklist.create', { ...draft, value });
    if (done === null) return;
    adding = false;
    say(done.created ? 'Строка заведена' : 'Такая строка уже была');
    draft = { kind: 'hr', value: '', reason: '' };
    return refresh();
  }

  /** Записать правку строки и показать то, что легло на самом деле.
   *
   * Перечитываем всегда, даже после отказа: поле правится на месте, и
   * отклонённое мостом значение осталось бы на экране — человек читал бы своё,
   * а отсев шёл бы по прежнему.
   */
  async function edit(row, part) {
    await ask('blacklist.update', { id: row.id, ...part });
    return refresh();
  }

  async function toggle(row, on) {
    await ask('blacklist.set_active', { id: row.id, active: on });
    return refresh();
  }

  async function drop(row) {
    leaving = null;
    const done = await ask('blacklist.delete', row.id);
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
  placeholder="Поиск по значению и причине"
  onsearch={(text) => (search = text)}
  {loaded}
  count={shown.length}
  words={['строка', 'строки', 'строк']}
  filtered={rows.length > 0}
  nothing="Ничего не найдено"
  empty="Чёрный список пуст"
>
  {#snippet actions()}
    <button class="btn primary" type="button" onclick={() => (adding = true)}>
      <span class="material-symbols-outlined">add</span>
      Строка
    </button>
  {/snippet}

  {#snippet filters()}
    <div class="kind-pills">
      {#each BLACKLIST_KINDS as one (one.key)}
        <button
          class="kind-pill"
          class:active={kind === one.key}
          type="button"
          onclick={() => (kind = one.key)}
        >
          {one.label}
        </button>
      {/each}
    </div>
  {/snippet}

  {#each shown as row (`${row.id}:${row.value}:${row.reason}`)}
    <div class="blacklist-row" class:off={!row.active}>
      <span class="kind-tag" data-kind={row.kind}>{row.kind}</span>
      <input
        class="blacklist-value"
        value={row.value}
        onblur={(event) => edit(row, { value: event.currentTarget.value.trim() })}
      />
      <input
        class="blacklist-reason"
        placeholder="Причина"
        value={row.reason || ''}
        onblur={(event) => edit(row, { reason: event.currentTarget.value.trim() })}
      />
      <input
        type="checkbox"
        class="toggle"
        checked={row.active}
        title="Строка действует"
        onchange={(event) => toggle(row, event.currentTarget.checked)}
      />
      <button class="icon-btn" type="button" title="Удалить" onclick={() => (leaving = row)}>
        <span class="material-symbols-outlined">delete</span>
      </button>
    </div>
  {/each}
</SearchList>

{#if adding}
  <AskDialog
    icon="block"
    title="Новая строка отсева"
    confirmLabel="Добавить"
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <div class="kind-pills">
      {#each BLACKLIST_KINDS.filter((one) => one.key) as one (one.key)}
        <button
          class="kind-pill"
          class:active={draft.kind === one.key}
          type="button"
          onclick={() => (draft = { ...draft, kind: one.key })}
        >
          {one.label}
        </button>
      {/each}
    </div>

    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="input"
      autofocus
      placeholder="Значение: ник, название или слово"
      bind:value={draft.value}
      onkeydown={(event) => event.key === 'Enter' && create()}
    />
    <input class="input" placeholder="Причина (необязательно)" bind:value={draft.reason} />
  </AskDialog>
{/if}

{#if leaving}
  <ConfirmDialog
    message={`Убрать «${leaving.value}» из чёрного списка?\n\nОтсев по этой строке перестанет действовать сразу.`}
    confirmLabel="Убрать"
    onconfirm={() => drop(leaving)}
    oncancel={() => (leaving = null)}
  />
{/if}

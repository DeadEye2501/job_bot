<script>
  // Вкладка «Чёрный список»: строки отсева с отбором по роду и поиском.
  //
  // Отбор идёт у себя, а не на мосту: строк мало, мост шлёт их разом, и
  // спрашивать его на каждый набранный знак значило бы ждать сеть ради того,
  // что уже лежит в памяти.

  import AddBlacklistDialog from '$components/AddBlacklistDialog.svelte';
  import BlacklistRow from '$components/BlacklistRow.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import Dropdown from '$components/Dropdown.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { living } from '$state/alive.js';
  import {
    BLACKLIST_KINDS,
    blacklistCounts,
    blacklistHints,
    blacklistShown,
    blankRow,
    kindIndex,
    kindOptions,
    kindPicked,
    valueField,
  } from '$state/blacklist.js';
  import { freshAnswer } from '$state/fresh.js';

  let { ask, say, events } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let kind = $state('');
  let search = $state('');
  let adding = $state(false);
  let draft = $state(blankRow());
  let saving = $state(false);
  // Существующие люди, компании и каналы для подсказчика — по роду и по разу:
  // перечень не меняется, пока окно открыто.
  let known = $state({});
  let leaving = $state(null);

  const alive = living();
  const freshList = freshAnswer(() => alive.now);
  const freshKnown = freshAnswer(() => alive.now);

  const shown = $derived(blacklistShown(rows, { kind, search }));
  const kindChoices = $derived(kindOptions(blacklistCounts(rows)));
  const field = $derived(valueField(draft.kind));
  const hints = $derived(
    field.hints
      ? blacklistHints({
        items: known[draft.kind] ?? null,
        rows,
        kind: draft.kind,
        typed: draft.value,
      })
      : null,
  );

  /** Перечитать строки отсева.
   *
   * Свой счёт попыток: перечитывают этот список все — правка поля, гашение
   * строки, удаление, заведение и весть от бота, — и ответы возвращаются
   * вразнобой. Лёгший поверх свежего старый вернул бы на экран только что
   * поправленное значение.
   */
  async function refresh() {
    const now = await freshList(() => ask('blacklist.list'));
    if (now === null) return;
    rows = now.items;
    loaded = true;
  }

  /** Прочитать существующие записи этого рода — для подсказчика.
   *
   * Свой счёт попыток: род успевают сменить, пока летит ответ, и пришедший на
   * прежний вопрос показал бы каналы там, где выбраны люди.
   */
  async function load(one) {
    if (known[one] !== undefined) return;
    const now = await freshKnown(() => ask('blacklist.candidates', one));
    if (now === null) return;
    known = { ...known, [now.kind]: now.items };
  }

  function chooseKind(one) {
    draft = { ...draft, kind: one };
    if (valueField(one).hints) load(one);
  }

  async function create() {
    const value = draft.value.trim();
    if (!value || saving) return;
    saving = true;
    const done = await ask('blacklist.create', { ...draft, value });
    saving = false;
    if (done === null) return;
    adding = false;
    say(done.created ? 'Строка заведена' : 'Такая строка уже была');
    draft = blankRow();
    return refresh();
  }

  /** Записать правку строки и вернуть ответ моста.
   *
   * Перечитываем всегда, даже после отказа: поле правится на месте, и
   * отклонённое мостом значение осталось бы на экране — человек читал бы своё,
   * а отсев шёл бы по прежнему. Ответ уходит обратно в строку: по нему она и
   * решает, вспыхнуть ли зелёным.
   */
  async function edit(row, part) {
    const done = await ask('blacklist.update', { id: row.id, ...part });
    await refresh();
    return done;
  }

  /** Погасить строку отсева или зажечь её обратно.
   *
   * Отвечает, легло ли: строка держит положение переключателя у себя, и без
   * ответа отказ остался бы невидимым — переключатель показывал бы одно, а
   * отсев работал бы по-другому.
   */
  async function toggle(row, on) {
    const done = await ask('blacklist.set_active', { id: row.id, active: on });
    await refresh();
    return done !== null;
  }

  async function drop(row) {
    leaving = null;
    const done = await ask('blacklist.delete', row.id);
    if (done === null) return;
    return refresh();
  }

  $effect(() => {
    const settled = alive.entered(refresh);
    // Списки меняет не только этот экран: бот заносит людей и компании в отсев
    // сам, разбирая переписку. Без этой подписки экран показывал бы снимок той
    // минуты, когда его открыли.
    const deaf = events.on('contacts_lists_changed', refresh);
    return () => {
      settled();
      deaf();
    };
  });
</script>

<div class="bl-toolbar">
  <SearchBox
    value={search}
    placeholder="Поиск по значению или причине..."
    onsearch={(text) => (search = text)}
  />

  <div class="bl-kind-pick">
    <Dropdown
      options={kindChoices}
      value={kindChoices[kindIndex(kind)]}
      onpick={(picked) => (kind = kindPicked(kindChoices, picked))}
    />
  </div>

  <button class="btn bl-add-btn" type="button" title="Добавить в blacklist" onclick={() => (adding = true)}>
    <span class="material-symbols-outlined">add</span>
    Добавить
  </button>
</div>

{#if !loaded}
  <div class="empty-note cnt-list-empty">Загрузка…</div>
{:else if shown.length === 0}
  <div class="empty-note cnt-list-empty">{rows.length === 0 ? 'Blacklist пуст' : 'Ничего не найдено'}</div>
{:else}
  <div class="bl-table">
    <div class="bl-row head">
      <span>Тип</span>
      <span>Значение</span>
      <span>Причина</span>
      <span>Добавлено</span>
      <span class="bl-active-head">Активно</span>
      <span></span>
    </div>

    {#each shown as row (row.id)}
      <BlacklistRow
        {row}
        onedit={(part) => edit(row, part)}
        ontoggle={(on) => toggle(row, on)}
        onremove={() => (leaving = row)}
      />
    {/each}
  </div>
{/if}

{#if adding}
  <AddBlacklistDialog
    draft={{ ...draft, placeholder: field.placeholder }}
    {hints}
    {saving}
    kinds={BLACKLIST_KINDS.filter((one) => one.key).map((one) => one.key)}
    onkind={chooseKind}
    onvalue={(text) => (draft = { ...draft, value: text })}
    onreason={(text) => (draft = { ...draft, reason: text })}
    onadd={create}
    onclose={() => (adding = false)}
  />
{/if}

{#if leaving}
  <ConfirmDialog
    message={`Удалить «${leaving.value}» (${leaving.kind}) из blacklist?\n\nДействие необратимо.`}
    confirmLabel="Удалить"
    onconfirm={() => drop(leaving)}
    oncancel={() => (leaving = null)}
  />
{/if}

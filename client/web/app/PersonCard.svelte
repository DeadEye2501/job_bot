<script>
  // Карточка человека: его числа, поля и действия над ним.
  //
  // Переписка сюда приедет вторым заходом слайса; пока карточка рассказывает
  // то, что знает про человека сам список контактов.

  import CardDialog from '$components/CardDialog.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MergePicker from '$components/MergePicker.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import PersonRow from '$components/PersonRow.svelte';
  import { personName } from '$state/contacts.js';
  import { plural } from '$state/words.js';

  let { ask, say, personId, onclose, onchanged } = $props();

  let card = $state(null);
  let vacancies = $state([]);
  let trouble = $state('');
  let asking = $state(null);
  let chosen = $state(null);

  let alive = true;

  const shown = $derived(card ? personName({ ...card, id: card.hr_id }) : '');
  const chosenName = $derived(chosen ? personName(chosen) : '');

  async function refresh() {
    const now = await ask('hr.detail', personId);
    if (!alive) return;
    if (now === null) return (trouble = 'Не удалось прочитать карточку');
    card = now;
  }

  async function loadVacancies() {
    const now = await ask('hr.vacancies', { hr_id: personId });
    if (now === null || !alive) return;
    vacancies = now.vacancies;
  }

  /** Записать правку поля и показать то, что легло на самом деле.
   *
   * Перечитываем и после отказа: поля правятся на месте, и отклонённое мостом
   * значение — а негодный ник мост отклоняет — осталось бы на экране.
   */
  async function save(part) {
    const done = await ask('hr.update', { hr_id: personId, ...part });
    await refresh();
    if (done !== null) onchanged();
  }

  async function block() {
    const done = await ask('hr.block', personId);
    if (done === null) return;
    if (done.was_inactive) say(`Возвращён в отсев: ${done.value}`);
    else if (done.existed) say(`Уже в отсеве: ${done.value}`);
    else say(`Занесён в отсев: ${done.value}`);
    await refresh();
    onchanged();
  }

  async function unblock() {
    const done = await ask('hr.unblock', personId);
    if (done === null) return;
    say(done.updated ? 'Убран из отсева' : 'В отсеве его не было');
    await refresh();
    onchanged();
  }

  async function drop() {
    asking = null;
    const done = await ask('hr.delete', personId);
    if (done === null) return;
    say('Карточка удалена');
    onchanged();
    onclose();
  }

  async function candidates(search) {
    const now = await ask('hr.merge_picker', { absorbed_id: personId, search });
    return now === null ? null : now.hrs;
  }

  async function merge() {
    const survivor = chosen;
    chosen = null;
    const done = await ask('hr.merge', { absorbed_id: personId, survivor_id: survivor.id });
    if (done === null) return;
    asking = null;
    say('Карточки слиты');
    onchanged();
    onclose();
  }

  $effect(() => {
    alive = true;
    refresh();
    loadVacancies();
    return () => {
      alive = false;
    };
  });
</script>

<CardDialog {trouble} ready={!!card} {onclose}>
  <div class="modal-title card-head">
    {#if card.avatar}
      <img class="avatar" src={card.avatar} alt="" />
    {:else}
      <span class="avatar avatar-empty material-symbols-outlined">person</span>
    {/if}
    <span class="card-name">{shown}</span>
    {#if card.blacklist_value}
      <span class="kind-tag" data-kind="hr" title="В чёрном списке: {card.blacklist_value}">
        в отсеве: {card.blacklist_value}
      </span>
    {/if}
  </div>

  <div class="card-meta">
    <span class="card-meta-item">
      <span class="material-symbols-outlined">work</span>
      {card.vacancy_count} {plural(card.vacancy_count, 'вакансия', 'вакансии', 'вакансий')}
    </span>
    {#if card.last_company_name}
      <span class="card-meta-item">
        <span class="material-symbols-outlined">domain</span>
        {card.last_company_name}
      </span>
    {/if}
    {#if card.unread_count}
      <span class="card-meta-item">
        <span class="material-symbols-outlined">mail</span>
        {card.unread_count} {plural(card.unread_count, 'непрочитанное', 'непрочитанных', 'непрочитанных')}
      </span>
    {/if}
  </div>

  <div class="form-grid">
    <input
      class="input"
      value={card.name ?? ''}
      placeholder="Имя"
      onchange={(event) => save({ name: event.currentTarget.value.trim() })}
    />
    <input
      class="input"
      value={card.telegram_username ?? ''}
      placeholder="Ник в Telegram"
      onchange={(event) => save({ telegram_username: event.currentTarget.value.trim() })}
    />
  </div>

  <textarea
    class="textarea"
    placeholder="Заметки о человеке"
    value={card.notes ?? ''}
    onchange={(event) => save({ notes: event.currentTarget.value })}
  ></textarea>

  <MiniVacancies {vacancies} empty="Вакансий от этого человека ещё нет" />

  <div class="modal-actions card-actions">
    <button class="btn" type="button" onclick={() => (asking = 'merge')}>
      <span class="material-symbols-outlined">merge</span>
      Слить с другим
    </button>
    {#if card.blacklist_value}
      <button class="btn" type="button" onclick={unblock}>
        <span class="material-symbols-outlined">restart_alt</span>
        Убрать из отсева
      </button>
    {:else}
      <button class="btn danger" type="button" onclick={block}>
        <span class="material-symbols-outlined">block</span>
        В чёрный список
      </button>
    {/if}
    <button class="btn danger" type="button" onclick={() => (asking = 'delete')}>
      <span class="material-symbols-outlined">delete</span>
      Удалить
    </button>
    <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
  </div>
</CardDialog>

{#if asking === 'delete'}
  <ConfirmDialog
    message={`Удалить карточку «${shown}»?\n\nПереписка с ним удалится вместе с ней. Собранные вакансии останутся, но без человека. Откатить нельзя.`}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = null)}
  />
{/if}

{#if asking === 'merge'}
  <MergePicker
    title={`Слить «${shown}» с другим`}
    placeholder="Поиск по имени и нику"
    words={['человек', 'человека', 'человек']}
    empty="Сливать не с кем — других карточек нет"
    load={candidates}
    onclose={() => (asking = null)}
  >
    {#snippet children(rows)}
      {#each rows as person (person.id)}
        <PersonRow {person} onpick={() => (chosen = person)} />
      {/each}
    {/snippet}
  </MergePicker>
{/if}

{#if chosen}
  <!-- Про переписку сказано по-разному не для красоты: у выжившего со своей
       учётной записью Telegram чужая переписка стирается, а не переезжает
       (`hr_card._move_or_drop_chat`), и это необратимо. -->
  <ConfirmDialog
    message={chosen.telegram_user_id
      ? `Слить «${shown}» в «${chosenName}»?\n\nВакансии перейдут к выбранному. Переписка этой карточки будет удалена: у выбранного своя учётная запись Telegram и своя переписка. Эта карточка будет удалена. Откатить нельзя.`
      : `Слить «${shown}» в «${chosenName}»?\n\nВакансии и переписка перейдут к выбранному. Эта карточка будет удалена. Откатить нельзя.`}
    confirmLabel="Слить"
    onconfirm={merge}
    oncancel={() => (chosen = null)}
  />
{/if}

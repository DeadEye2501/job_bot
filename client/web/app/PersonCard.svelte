<script>
  // Карточка человека: его числа, поля и действия над ним.
  //
  // Стоит правой панелью рядом со списком: человека правят и пишут ему, не
  // теряя из виду соседей, — рядом с ними и решают, кому писать следующему.

  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { attempts } from '$state/attempts.js';
  import { personCandidate, personName } from '$state/contacts.js';
  import { plural } from '$state/words.js';

  import PersonChat from './PersonChat.svelte';

  let { ask, say, events, personId, onclose, onchanged } = $props();

  let card = $state(null);
  let vacancies = $state([]);
  let trouble = $state('');
  let asking = $state(null);
  let chosen = $state(null);

  // Свой счёт попыток на каждый вопрос: панель живёт одна на всю вкладку, и
  // человека в ней переключают нажатием по соседней строке — ответ про
  // прежнего, лёгший поверх свежего, показал бы его числа под новым именем.
  const cardTries = attempts();
  const vacancyTries = attempts();
  let alive = true;

  const shown = $derived(card ? personName({ ...card, id: card.hr_id }) : '');
  const chosenName = $derived(chosen ? personName(chosen) : '');

  async function refresh(id) {
    const mine = cardTries.next();
    const now = await ask('hr.detail', id);
    if (!alive || cardTries.stale(mine)) return;
    if (now === null) return (trouble = 'Не удалось прочитать карточку');
    card = now;
  }

  async function loadVacancies(id) {
    const mine = vacancyTries.next();
    const now = await ask('hr.vacancies', { hr_id: id });
    if (now === null || !alive || vacancyTries.stale(mine)) return;
    vacancies = now.vacancies;
  }

  /** Записать правку поля и показать то, что легло на самом деле.
   *
   * Перечитываем и после отказа: поля правятся на месте, и отклонённое мостом
   * значение — а негодный ник мост отклоняет — осталось бы на экране.
   */
  async function save(part) {
    const done = await ask('hr.update', { hr_id: personId, ...part });
    await refresh(personId);
    if (done !== null) onchanged();
  }

  async function block() {
    const done = await ask('hr.block', personId);
    if (done === null) return;
    if (done.was_inactive) say(`Возвращён в отсев: ${done.value}`);
    else if (done.existed) say(`Уже в отсеве: ${done.value}`);
    else say(`Занесён в отсев: ${done.value}`);
    await refresh(personId);
    onchanged();
  }

  async function unblock() {
    const done = await ask('hr.unblock', personId);
    if (done === null) return;
    say(done.updated ? 'Убран из отсева' : 'В отсеве его не было');
    await refresh(personId);
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
    const id = personId;
    // Показанное прежним человеком уходит сразу: панель одна, и его числа под
    // новым именем читались бы как числа нового.
    card = null;
    trouble = '';
    vacancies = [];
    refresh(id);
    loadVacancies(id);
    return () => {
      alive = false;
    };
  });
</script>

{#if trouble}
  <div class="cnt-detail-empty">{trouble}</div>
{:else if !card}
  <div class="cnt-detail-empty">Загрузка…</div>
{:else}
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

  <PersonChat
    {ask}
    {say}
    {events}
    {card}
    onread={async () => {
      await refresh(personId);
      onchanged();
    }}
  />

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
  </div>
{/if}

{#if asking === 'delete'}
  <ConfirmDialog
    message={`Удалить карточку «${shown}»?\n\nПереписка с ним удалится вместе с ней. Собранные вакансии останутся, но без человека. Откатить нельзя.`}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = null)}
  />
{/if}

{#if asking === 'merge'}
  <PickerDialog
    icon="merge"
    title={`Слить «${shown}» с другим`}
    placeholder="Поиск по имени и нику"
    empty="Сливать не с кем — других карточек нет"
    load={candidates}
    applyLabel="Слить"
    onapply={(person) => (chosen = person)}
    onclose={() => (asking = null)}
  >
    {#snippet children(rows, marked, pick)}
      {#each rows as person (person.id)}
        <PickerRow row={personCandidate(person)} chosen={person.id === marked} onpick={pick} />
      {/each}
    {/snippet}
  </PickerDialog>
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

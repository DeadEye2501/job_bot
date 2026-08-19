<script>
  // Карточка человека: его числа, поля, переписка и действия над ним.
  //
  // Стоит правой панелью рядом со списком: человека правят и пишут ему, не
  // теряя из виду соседей, — рядом с ними и решают, кому писать следующему.

  import ActionsMenu from '$components/ActionsMenu.svelte';
  import Avatar from '$components/Avatar.svelte';
  import BlacklistMenuItem from '$components/BlacklistMenuItem.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import NotesField from '$components/NotesField.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { attempts } from '$state/attempts.js';
  import { personCandidate, personName, telegramHref } from '$state/contacts.js';
  import { plural } from '$state/words.js';

  import PersonChat from './PersonChat.svelte';

  // Пауза перед записью заметки — та же, что ждало прежнее окно.
  const NOTES_DELAY = 600;

  let { ask, say, events, personId, oncompany, onvacancy, onclose, onchanged } = $props();

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

  /** Записать заметку и вернуть то, что легло в базу.
   *
   * Карточку не перечитываем: человек мог набрать ещё, пока летел вопрос, и
   * пришедшее из базы стёрло бы это. Записанным считаем набранное: этот зов
   * называет только поправленные поля, самой заметки в ответе нет, — а пустая
   * от пробельной здесь не отличается, обе сводятся к пустоте по дороге.
   */
  async function saveNotes(id, text) {
    const done = await ask('hr.update', { hr_id: id, notes: text });
    if (!alive || done === null) return null;
    onchanged();
    return text;
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
  <div class="cnt-det-head">
    <Avatar avatar={card.avatar} name={card.name} icon="person" />

    <div>
      <div class="cnt-det-name" class:muted={!card.name}>{card.name || '— без имени —'}</div>

      <div class="cnt-det-sub">
        {#if card.telegram_username}
          <button
            class="cnt-det-link"
            type="button"
            title="Открыть в Telegram"
            onclick={() => ask('system.open_url', telegramHref(card.telegram_username))}
          >
            @{card.telegram_username}
          </button>
        {:else}
          <span>@—</span>
        {/if}
        {#if card.last_company_name}
          <span>·</span>
          {#if card.last_company_id === null}
            <span>{card.last_company_name}</span>
          {:else}
            <button
              class="cnt-det-link"
              type="button"
              onclick={() => oncompany(card.last_company_id)}
            >
              {card.last_company_name}
            </button>
          {/if}
        {/if}
      </div>

      <div class="cnt-det-meta-row">
        {#if card.unread_count}
          <span class="cnt-det-meta-chip unread">
            <span class="material-symbols-outlined">mail</span>
            {card.unread_count}
            {plural(card.unread_count, 'непрочитанное', 'непрочитанных', 'непрочитанных')}
          </span>
        {/if}
        {#if card.blacklist_value}
          <span class="cnt-det-meta-chip blacklist" title="В blacklist: {card.blacklist_value}">
            <span class="material-symbols-outlined">block</span>
            В blacklist
          </span>
        {/if}
      </div>
    </div>

    <ActionsMenu>
      {#snippet children(close)}
        <button
          class="menu-item"
          type="button"
          onclick={() => {
            close();
            asking = 'merge';
          }}
        >
          <span class="material-symbols-outlined">merge</span>
          Слить с другим HR
        </button>
        <BlacklistMenuItem
          blocked={!!card.blacklist_value}
          {close}
          onblock={block}
          onunblock={unblock}
        />

        <div class="menu-line"></div>

        <button
          class="menu-item danger"
          type="button"
          onclick={() => {
            close();
            asking = 'delete';
          }}
        >
          <span class="material-symbols-outlined">delete</span>
          Удалить
        </button>
      {/snippet}
    </ActionsMenu>
  </div>

  <div class="cnt-form-grid">
    <input
      class="cnt-input"
      maxlength="120"
      value={card.name ?? ''}
      placeholder="Имя"
      onchange={(event) => save({ name: event.currentTarget.value.trim() })}
    />
    <input
      class="cnt-input"
      maxlength="64"
      value={card.telegram_username ? `@${card.telegram_username}` : ''}
      placeholder="Telegram @username"
      onchange={(event) => save({ telegram_username: event.currentTarget.value.trim() })}
    />
  </div>

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

  <div class="cnt-det-section">
    <!-- Своя запись на каждого человека: поле запечатывает номер при
         заведении, и заводиться заново на каждого его заставляет именно
         `{#key}` — без него запечатанный номер протухнет. -->
    {#key personId}
      <NotesField
        value={card.notes}
        placeholder="Личные заметки по этому HR…"
        delay={NOTES_DELAY}
        limit={2000}
        owner={personId}
        save={saveNotes}
      />
    {/key}
  </div>

  <MiniVacancies {vacancies} empty="Связанных вакансий нет." onpick={onvacancy} />
{/if}

{#if asking === 'delete'}
  <ConfirmDialog
    message={`Удалить HR «${shown}»?\n\nВся переписка удалится. Связанные вакансии останутся, но без HR.`}
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

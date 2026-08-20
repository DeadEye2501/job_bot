<script>
  // Карточка человека: его числа, поля, переписка и действия над ним.
  //
  // Стоит правой панелью рядом со списком: человека правят и пишут ему, не
  // теряя из виду соседей, — рядом с ними и решают, кому писать следующему.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import ContactActions from '$components/ContactActions.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import NotesField from '$components/NotesField.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { living } from '$state/alive.js';
  import { blockNote, unblockNote } from '$state/blacklist.js';
  import { cardDrop } from '$state/card_drop.js';
  import { cardRead } from '$state/card_read.js';
  import { sendBlock } from '$state/chat.js';
  import { freshAnswer } from '$state/fresh.js';
  import { personCandidate, personName } from '$state/people.js';
  import { telegramHref } from '$state/telegram.js';
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
  const alive = living();
  const freshVacancies = freshAnswer(() => alive.now);

  const readCard = cardRead({
    ask: (...args) => ask(...args),
    method: 'hr.detail',
    trouble: 'Не удалось прочитать карточку',
    alive: () => alive.now,
  });

  const dropCard = cardDrop({
    ask: (...args) => ask(...args),
    method: 'hr.delete',
    note: 'Карточка удалена',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const shown = $derived(card ? personName({ ...card, id: card.hr_id }) : '');
  const chosenName = $derived(chosen ? personName(chosen) : '');

  async function refresh(id) {
    const now = await readCard(id);
    if (now === null) return;
    ({ card, trouble } = now);
  }

  async function loadVacancies(id) {
    const now = await freshVacancies(() => ask('hr.vacancies', { hr_id: id }));
    if (now === null) return;
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
    if (!alive.now || done === null) return null;
    onchanged();
    return text;
  }

  async function block() {
    const done = await ask('hr.block', personId);
    if (done === null) return;
    say(blockNote(done));
    await refresh(personId);
    onchanged();
  }

  async function unblock() {
    const done = await ask('hr.unblock', personId);
    if (done === null) return;
    say(unblockNote(done));
    await refresh(personId);
    onchanged();
  }

  async function drop() {
    asking = null;
    await dropCard(personId);
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
    const settled = alive.mounted();
    const id = personId;
    // Показанное прежним человеком уходит сразу: панель одна, и его числа под
    // новым именем читались бы как числа нового.
    card = null;
    trouble = '';
    vacancies = [];
    refresh(id);
    loadVacancies(id);
    return () => {
      settled();
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
        <BlacklistChip value={card.blacklist_value} />
      </div>
    </div>

    <ContactActions
      mergeLabel="Слить с другим HR"
      blocked={!!card.blacklist_value}
      onmerge={() => (asking = 'merge')}
      onblock={block}
      onunblock={unblock}
      ondelete={() => (asking = 'delete')}
    />
  </div>

  <div class="cnt-form-grid">
    <input
      class="input cnt-input"
      maxlength="120"
      value={card.name ?? ''}
      placeholder="Имя"
      onchange={(event) => save({ name: event.currentTarget.value.trim() })}
    />
    <input
      class="input cnt-input"
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
    hrId={card.hr_id}
    blocked={sendBlock(card)}
    onread={async () => {
      await refresh(personId);
      onchanged();
    }}
  />

  <div class="card-section">
    <!-- Своя запись на каждого человека: поле запечатывает номер при
         заведении, и заводиться заново на каждого его заставляет именно
         `{#key}` — без него запечатанный номер протухнет. -->
    {#key personId}
      <NotesField
        value={card.notes}
        placeholder="Личные заметки по этому HR…"
        delay={NOTES_DELAY}
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

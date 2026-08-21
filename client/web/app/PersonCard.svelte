<script>
  // Карточка человека: его числа, поля, переписка и действия над ним.
  //
  // Стоит правой панелью рядом со списком: человека правят и пишут ему, не
  // теряя из виду соседей, — рядом с ними и решают, кому писать следующему.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import CardHandle from '$components/CardHandle.svelte';
  import ContactActions from '$components/ContactActions.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import NotesField from '$components/NotesField.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { living } from '$state/alive.js';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { cardNotes } from '$state/card_notes.js';
  import { cardRead } from '$state/card_read.js';
  import { cardSave } from '$state/card_save.js';
  import { sendBlock } from '$state/chat.js';
  import { freshAnswer } from '$state/fresh.js';
  import { personCandidate, personHead, personName } from '$state/people.js';
  import { plural } from '$state/words.js';

  import PersonChat from './PersonChat.svelte';

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

  const dropCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'hr.delete',
    note: 'Карточка удалена',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const mergeCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'hr.merge',
    note: 'Карточки слиты',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const saveField = cardSave({
    ask: (...args) => ask(...args),
    method: 'hr.update',
    reread: () => refresh(personId),
    onchanged: () => onchanged(),
  });

  const saveNotes = cardNotes({
    ask: (...args) => ask(...args),
    method: 'hr.update',
    payload: (id, text) => ({ hr_id: id, notes: text }),
    alive: () => alive.now,
    onchanged: () => onchanged(),
  });

  const blocking = cardBlocking({
    ask: (...args) => ask(...args),
    block: 'hr.block',
    unblock: 'hr.unblock',
    say: (text) => say(text),
    reread: () => refresh(personId),
    onchanged: () => onchanged(),
  });

  const shown = $derived(card ? personName({ ...card, id: card.hr_id }) : '');
  const head = $derived(card ? personHead(card) : null);
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

  function save(part) {
    return saveField({ hr_id: personId, ...part });
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
    // Окно выбора гасим только по удаче: отказ оставляет выбранного под рукой,
    // а закрытое окно заставило бы искать его заново.
    if (await mergeCard({ absorbed_id: personId, survivor_id: survivor.id })) asking = null;
  }

  $effect(() =>
    alive.entered(() => {
      const id = personId;
      // Показанное прежним человеком уходит сразу: панель одна, и его числа под
      // новым именем читались бы как числа нового.
      card = null;
      trouble = '';
      vacancies = [];
      refresh(id);
      loadVacancies(id);
    }),
  );
</script>

{#if trouble}
  <div class="empty-note cnt-detail-empty">{trouble}</div>
{:else if !card}
  <div class="empty-note cnt-detail-empty">Загрузка…</div>
{:else}
  <div class="cnt-det-head">
    <Avatar avatar={card.avatar} name={card.name} icon="person" />

    <div>
      <div class="cnt-det-name" class:muted={!head.named}>{head.name}</div>

      <div class="cnt-det-sub">
        <CardHandle
          username={card.telegram_username}
          onopen={(url) => ask('system.open_url', url)}
        />
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
      onblock={() => blocking.block(personId)}
      onunblock={() => blocking.unblock(personId)}
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

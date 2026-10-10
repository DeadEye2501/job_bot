<script>
  // Карточка человека: его числа, поля, переписка и действия над ним.
  //
  // Стоит правой панелью рядом со списком: человека правят и пишут ему, не
  // теряя из виду соседей, — рядом с ними и решают, кому писать следующему.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import CardHandle from '$components/CardHandle.svelte';
  import CardPane from '$components/CardPane.svelte';
  import ContactActions from '$components/ContactActions.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MergeDialog from '$components/MergeDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import NotesField from '$components/NotesField.svelte';
  import { living } from '$state/alive.js';
  import { cardActions } from '$state/card_actions.svelte.js';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { cardNotes } from '$state/card_notes.js';
  import { cardRead } from '$state/card_read.js';
  import { cardSave } from '$state/card_save.js';
  import { sendBlock } from '$state/chat.js';
  import { miniRead } from '$state/mini_read.js';
  import { personCandidate, personHead, personName } from '$state/people.js';
  import { plural } from '$state/words.js';

  import PersonChat from './PersonChat.svelte';

  let { ask, say, events, personId, oncompany, onvacancy, onclose, onchanged } = $props();

  let card = $state(null);
  let vacancies = $state([]);
  let trouble = $state('');

  // Свой счёт попыток на каждый вопрос: панель живёт одна на всю вкладку, и
  // человека в ней переключают нажатием по соседней строке — ответ про
  // прежнего, лёгший поверх свежего, показал бы его числа под новым именем.
  const alive = living();
  const loadVacancies = miniRead({
    ask: (...args) => ask(...args),
    alive: () => alive.now,
    method: 'hr.vacancies',
    payload: (id) => ({ hr_id: id }),
    key: 'vacancies',
    show: (rows) => (vacancies = rows),
  });

  const readCard = cardRead({
    ask: (...args) => ask(...args),
    method: 'hr.detail',
    trouble: 'Не удалось прочитать карточку',
    alive: () => alive.now,
    show: (now) => ({ card, trouble } = now),
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
    reread: () => readCard(personId),
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
    block: (id) => ask('hr.block', id),
    unblock: (id) => ask('hr.unblock', id),
    say: (text) => say(text),
    reread: () => readCard(personId),
    onchanged: () => onchanged(),
  });

  const acts = cardActions({ id: () => personId, dropCard, mergeCard });

  const shown = $derived(card ? personName({ ...card, id: card.hr_id }) : '');
  const head = $derived(card ? personHead(card) : null);
  const chosenName = $derived(acts.chosen ? personName(acts.chosen) : '');

  function save(part) {
    return saveField({ hr_id: personId, ...part });
  }

  async function candidates(search) {
    const now = await ask('hr.merge_picker', { absorbed_id: personId, search });
    return now === null ? null : now.hrs;
  }

  $effect(() => {
    const id = personId;
    return alive.entered(() => {
      // Показанное прежним человеком уходит сразу: панель одна, и его числа под
      // новым именем читались бы как числа нового.
      card = null;
      trouble = '';
      vacancies = [];
      readCard(id);
      loadVacancies(id);
    });
  });
</script>

<CardPane {trouble} ready={!!card}>
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
      onmerge={() => (acts.asking = 'merge')}
      onblock={() => blocking.block(personId)}
      onunblock={() => blocking.unblock(personId)}
      ondelete={() => (acts.asking = 'delete')}
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
      await readCard(personId);
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
</CardPane>

{#if acts.asking === 'delete'}
  <ConfirmDialog
    message={`Удалить HR «${shown}»?\n\nВся переписка удалится. Связанные вакансии останутся, но без HR.`}
    confirmLabel="Удалить"
    onconfirm={() => acts.drop()}
    oncancel={() => (acts.asking = null)}
  />
{/if}

{#if acts.asking === 'merge'}
  <MergeDialog
    title={`Слить «${shown}» с другим`}
    placeholder="Поиск по имени и нику"
    empty="Сливать не с кем — других карточек нет"
    load={candidates}
    asRow={personCandidate}
    onapply={(person) => (acts.chosen = person)}
    onclose={() => (acts.asking = null)}
  />
{/if}

{#if acts.chosen}
  <!-- Про переписку сказано по-разному не для красоты: у выжившего со своей
       учётной записью Telegram чужая переписка стирается, а не переезжает
       (`hr_card._move_or_drop_chat`), и это необратимо. -->
  <ConfirmDialog
    message={acts.chosen.telegram_user_id
      ? `Слить «${shown}» в «${chosenName}»?\n\nВакансии перейдут к выбранному. Переписка этой карточки будет удалена: у выбранного своя учётная запись Telegram и своя переписка. Эта карточка будет удалена. Откатить нельзя.`
      : `Слить «${shown}» в «${chosenName}»?\n\nВакансии и переписка перейдут к выбранному. Эта карточка будет удалена. Откатить нельзя.`}
    confirmLabel="Слить"
    onconfirm={() => acts.merge()}
    oncancel={() => (acts.chosen = null)}
  />
{/if}

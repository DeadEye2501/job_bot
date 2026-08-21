<script>
  // Карточка компании: её числа, поля, люди и вакансии.
  //
  // Стоит правой панелью рядом со списком: компанию правят, глядя на её же
  // людей и вакансии, и уводить ради этого с экрана значило бы терять из виду
  // соседей по списку.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import ContactActions from '$components/ContactActions.svelte';
  import ChipList from '$components/ChipList.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniPeople from '$components/MiniPeople.svelte';
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
  import { companyCandidate, companyLine, companyTitle, siteHref } from '$state/companies.js';
  import { miniRead } from '$state/mini_read.js';

  let { ask, say, companyId, onperson, onvacancy, onclose, onchanged } = $props();

  let card = $state(null);
  let people = $state([]);
  let vacancies = $state([]);
  let trouble = $state('');
  let asking = $state(null);
  let chosen = $state(null);

  // Свой счёт попыток на каждый вопрос: панель живёт одна на всю вкладку, и
  // компанию в ней переключают нажатием по соседней строке — ответ про
  // прежнюю, лёгший поверх свежего, показал бы её числа под новым именем.
  const alive = living();
  const loadPeople = miniRead({
    ask: (...args) => ask(...args),
    alive: () => alive.now,
    method: 'companies.people',
    payload: (id) => id,
    key: 'hrs',
    show: (rows) => (people = rows),
  });
  const loadVacancies = miniRead({
    ask: (...args) => ask(...args),
    alive: () => alive.now,
    method: 'companies.vacancies',
    payload: (id) => ({ company_id: id }),
    key: 'vacancies',
    show: (rows) => (vacancies = rows),
  });

  const readCard = cardRead({
    ask: (...args) => ask(...args),
    method: 'companies.detail',
    trouble: 'Не удалось прочитать компанию',
    alive: () => alive.now,
    show: (now) => ({ card, trouble } = now),
  });

  const dropCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'companies.delete',
    note: 'Компания удалена',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const mergeCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'companies.merge',
    note: 'Компании слиты',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const saveField = cardSave({
    ask: (...args) => ask(...args),
    method: 'companies.update',
    reread: () => readCard(companyId),
    onchanged: () => onchanged(),
  });

  const saveNotes = cardNotes({
    ask: (...args) => ask(...args),
    method: 'companies.update',
    payload: (id, text) => ({ company_id: id, notes: text }),
    alive: () => alive.now,
    onchanged: () => onchanged(),
  });

  const blocking = cardBlocking({
    ask: (...args) => ask(...args),
    block: 'companies.block',
    unblock: 'companies.unblock',
    female: true,
    say: (text) => say(text),
    reread: () => readCard(companyId),
    onchanged: () => onchanged(),
  });

  const shown = $derived(card ? companyLine({ ...card, id: card.company_id }) : null);
  const head = $derived(card ? companyTitle(card) : null);
  const chosenName = $derived(chosen ? companyLine(chosen).name : '');
  const site = $derived(card ? siteHref(card.website) : null);

  function save(part) {
    return saveField({ company_id: companyId, ...part });
  }

  /** Поправить название. Пустое не отправляется вовсе: без названия компанию
   *  потом не найти ничем, и мост такую правку всё равно отобьёт. */
  function rename(event) {
    const value = event.currentTarget.value.trim();
    if (!value) {
      event.currentTarget.value = card.name;
      return;
    }
    return save({ name: value });
  }

  async function drop() {
    asking = null;
    await dropCard(companyId);
  }

  async function candidates(search) {
    const now = await ask('companies.merge_picker', { absorbed_id: companyId, search });
    return now === null ? null : now.companies;
  }

  async function merge() {
    const survivor = chosen;
    chosen = null;
    // Окно выбора гасим только по удаче: отказ оставляет выбранную под рукой,
    // а закрытое окно заставило бы искать её заново.
    if (await mergeCard({ absorbed_id: companyId, survivor_id: survivor.id })) asking = null;
  }

  $effect(() => {
    const id = companyId;
    return alive.entered(() => {
      // Показанное прежней компанией уходит сразу: панель одна, и её числа под
      // новым именем читались бы как числа новой.
      card = null;
      trouble = '';
      people = [];
      vacancies = [];
      readCard(id);
      loadPeople(id);
      loadVacancies(id);
    });
  });
</script>

{#if trouble}
  <div class="empty-note cnt-detail-empty">{trouble}</div>
{:else if !card}
  <div class="empty-note cnt-detail-empty">Загрузка…</div>
{:else}
  <div class="cnt-det-head">
    <Avatar icon="domain" />

    <div>
      <div class="cnt-det-name" class:muted={!head.named}>{head.name}</div>

      <div class="cnt-det-sub">
        {#if site === null}
          <span>сайт не указан</span>
        {:else}
          <button
            class="cnt-det-link"
            type="button"
            title="Открыть сайт"
            onclick={() => ask('system.open_url', site)}
          >
            {card.website}
          </button>
        {/if}
      </div>

      <div class="cnt-det-meta-row">
        <BlacklistChip value={card.blacklist_value} />
      </div>
    </div>

    <ContactActions
      mergeLabel="Слить с другой компанией"
      blocked={!!card.blacklist_value}
      onmerge={() => (asking = 'merge')}
      onblock={() => blocking.block(companyId)}
      onunblock={() => blocking.unblock(companyId)}
      ondelete={() => (asking = 'delete')}
    />
  </div>

  <div class="cnt-form-grid">
    <input class="input cnt-input" maxlength="120" value={card.name} placeholder="Название" onchange={rename} />
    <input
      class="input cnt-input"
      maxlength="200"
      value={card.website ?? ''}
      placeholder="Сайт / домен"
      onchange={(event) => save({ website: event.currentTarget.value.trim() })}
    />
  </div>

  <!-- Написания: под ними компания приходит в объявлениях. Потеряй карточка
       одно из них — следующая вакансия завела бы компанию заново. -->
  <div class="card-section">
    <ChipList
      items={card.aliases}
      onadd={(one) => save({ aliases: [...card.aliases, one] })}
      onremove={(index) => save({ aliases: card.aliases.filter((_, at) => at !== index) })}
    />
  </div>

  <div class="card-section">
    {#key companyId}
      <NotesField
        value={card.notes}
        placeholder="Заметки о компании…"
        owner={companyId}
        save={saveNotes}
      />
    {/key}
  </div>

  <MiniPeople {people} empty="HR-контактов нет." onpick={onperson} />

  <MiniVacancies {vacancies} empty="Связанных вакансий нет." onpick={onvacancy} />
{/if}

{#if asking === 'delete'}
  <ConfirmDialog
    message={`Удалить компанию «${shown.name}»?\n\nСобранные вакансии останутся, но без компании. Откатить нельзя.`}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = null)}
  />
{/if}

{#if asking === 'merge'}
  <PickerDialog
    icon="merge"
    title={`Слить «${shown.name}» с другой`}
    placeholder="Поиск по названию, написанию, домену"
    empty="Сливать не с чем — других компаний нет"
    load={candidates}
    applyLabel="Слить"
    onapply={(company) => (chosen = company)}
    onclose={() => (asking = null)}
  >
    {#snippet children(rows, marked, pick)}
      {#each rows as company (company.id)}
        <PickerRow row={companyCandidate(company)} chosen={company.id === marked} onpick={pick} />
      {/each}
    {/snippet}
  </PickerDialog>
{/if}

{#if chosen}
  <ConfirmDialog
    message={`Слить «${shown.name}» в «${chosenName}»?

Вакансии перейдут к выбранной. Написания объединятся — нынешнее имя станет одним из них. Заметки склеятся. Сайт возьмётся у выбранной, а если его там нет — у нынешней. Эта компания будет удалена. Откатить нельзя.`}
    confirmLabel="Слить"
    onconfirm={merge}
    oncancel={() => (chosen = null)}
  />
{/if}

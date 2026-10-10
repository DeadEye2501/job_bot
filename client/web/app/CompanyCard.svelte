<script>
  // Карточка компании: её числа, поля, люди и вакансии.
  //
  // Стоит правой панелью рядом со списком: компанию правят, глядя на её же
  // людей и вакансии, и уводить ради этого с экрана значило бы терять из виду
  // соседей по списку.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import CardPane from '$components/CardPane.svelte';
  import ContactActions from '$components/ContactActions.svelte';
  import ChipList from '$components/ChipList.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MergeDialog from '$components/MergeDialog.svelte';
  import MiniPeople from '$components/MiniPeople.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import NotesField from '$components/NotesField.svelte';
  import { living } from '$state/alive.js';
  import { cardActions } from '$state/card_actions.svelte.js';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { cardNotes } from '$state/card_notes.js';
  import { cardRead } from '$state/card_read.js';
  import { cardSave } from '$state/card_save.js';
  import { companyCandidate, companyLine, companyTitle } from '$state/companies.js';
  import { miniRead } from '$state/mini_read.js';
  import { siteHref } from '$state/site.js';

  let { ask, say, companyId, onperson, onvacancy, onclose, onchanged } = $props();

  let card = $state(null);
  let people = $state([]);
  let vacancies = $state([]);
  let trouble = $state('');

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
    block: (id) => ask('companies.block', id),
    unblock: (id) => ask('companies.unblock', id),
    female: true,
    say: (text) => say(text),
    reread: () => readCard(companyId),
    onchanged: () => onchanged(),
  });

  const acts = cardActions({ id: () => companyId, dropCard, mergeCard });

  const shown = $derived(card ? companyLine({ ...card, id: card.company_id }) : null);
  const head = $derived(card ? companyTitle(card) : null);
  const chosenName = $derived(acts.chosen ? companyLine(acts.chosen).name : '');
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

  async function candidates(search) {
    const now = await ask('companies.merge_picker', { absorbed_id: companyId, search });
    return now === null ? null : now.companies;
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

<CardPane {trouble} ready={!!card}>
  <div class="cnt-det-head">
    <Avatar icon="domain" />

    <div>
      <div class="cnt-det-name" class:muted={!head.named}>{head.name}</div>

      <div class="cnt-det-sub">
        {#if site === null}
          <span>сайт не указан</span>
        {:else}
          <button
            class="cnt-det-link link-hover"
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
      onmerge={() => (acts.asking = 'merge')}
      onblock={() => blocking.block(companyId)}
      onunblock={() => blocking.unblock(companyId)}
      ondelete={() => (acts.asking = 'delete')}
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
</CardPane>

{#if acts.asking === 'delete'}
  <ConfirmDialog
    message={`Удалить компанию «${shown.name}»?\n\nСобранные вакансии останутся, но без компании. Откатить нельзя.`}
    confirmLabel="Удалить"
    onconfirm={() => acts.drop()}
    oncancel={() => (acts.asking = null)}
  />
{/if}

{#if acts.asking === 'merge'}
  <MergeDialog
    title={`Слить «${shown.name}» с другой`}
    placeholder="Поиск по названию, написанию, домену"
    empty="Сливать не с чем — других компаний нет"
    load={candidates}
    asRow={companyCandidate}
    onapply={(company) => (acts.chosen = company)}
    onclose={() => (acts.asking = null)}
  />
{/if}

{#if acts.chosen}
  <ConfirmDialog
    message={`Слить «${shown.name}» в «${chosenName}»?

Вакансии перейдут к выбранной. Написания объединятся — нынешнее имя станет одним из них. Заметки склеятся. Сайт возьмётся у выбранной, а если его там нет — у нынешней. Эта компания будет удалена. Откатить нельзя.`}
    confirmLabel="Слить"
    onconfirm={() => acts.merge()}
    oncancel={() => (acts.chosen = null)}
  />
{/if}

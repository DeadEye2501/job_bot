<script>
  // Карточка компании: её числа, поля, люди и вакансии.
  //
  // Стоит правой панелью рядом со списком: компанию правят, глядя на её же
  // людей и вакансии, и уводить ради этого с экрана значило бы терять из виду
  // соседей по списку.

  import ActionsMenu from '$components/ActionsMenu.svelte';
  import Avatar from '$components/Avatar.svelte';
  import ChipList from '$components/ChipList.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniPeople from '$components/MiniPeople.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import NotesField from '$components/NotesField.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { attempts } from '$state/attempts.js';
  import { companyCandidate, companyLine, siteHref } from '$state/companies.js';

  // Пауза перед записью заметки — та же, что ждало прежнее окно.
  const NOTES_DELAY = 600;

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
  const cardTries = attempts();
  const peopleTries = attempts();
  const vacancyTries = attempts();
  let alive = true;

  const shown = $derived(card ? companyLine({ ...card, id: card.company_id }) : null);
  const chosenName = $derived(chosen ? companyLine(chosen).name : '');
  const site = $derived(card ? siteHref(card.website) : null);

  async function refresh(id) {
    const mine = cardTries.next();
    const now = await ask('companies.detail', id);
    if (!alive || cardTries.stale(mine)) return;
    if (now === null) return (trouble = 'Не удалось прочитать компанию');
    card = now;
  }

  async function loadPeople(id) {
    const mine = peopleTries.next();
    const now = await ask('companies.people', id);
    if (now === null || !alive || peopleTries.stale(mine)) return;
    people = now.hrs;
  }

  async function loadVacancies(id) {
    const mine = vacancyTries.next();
    const now = await ask('companies.vacancies', { company_id: id });
    if (now === null || !alive || vacancyTries.stale(mine)) return;
    vacancies = now.vacancies;
  }

  /** Записать правку поля и показать то, что легло на самом деле.
   *
   * Перечитываем и после отказа: поля правятся на месте, и отклонённое мостом
   * значение осталось бы на экране — человек читал бы своё, а в базе лежало бы
   * прежнее.
   */
  async function save(part) {
    const done = await ask('companies.update', { company_id: companyId, ...part });
    await refresh(companyId);
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
    const done = await ask('companies.update', { company_id: id, notes: text });
    if (!alive || done === null) return null;
    onchanged();
    return text;
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

  async function block() {
    const done = await ask('companies.block', companyId);
    if (done === null) return;
    if (done.was_inactive) say(`Возвращена в отсев: ${done.value}`);
    else if (done.existed) say(`Уже в отсеве: ${done.value}`);
    else say(`Занесена в отсев: ${done.value}`);
    await refresh(companyId);
    onchanged();
  }

  async function unblock() {
    const done = await ask('companies.unblock', companyId);
    if (done === null) return;
    say(done.updated ? 'Убрана из отсева' : 'В отсеве её не было');
    await refresh(companyId);
    onchanged();
  }

  async function drop() {
    asking = null;
    const done = await ask('companies.delete', companyId);
    if (done === null) return;
    say('Компания удалена');
    onchanged();
    onclose();
  }

  async function candidates(search) {
    const now = await ask('companies.merge_picker', { absorbed_id: companyId, search });
    return now === null ? null : now.companies;
  }

  async function merge() {
    const survivor = chosen;
    chosen = null;
    const done = await ask('companies.merge', {
      absorbed_id: companyId,
      survivor_id: survivor.id,
    });
    if (done === null) return;
    asking = null;
    say('Компании слиты');
    onchanged();
    onclose();
  }

  $effect(() => {
    alive = true;
    const id = companyId;
    // Показанное прежней компанией уходит сразу: панель одна, и её числа под
    // новым именем читались бы как числа новой.
    card = null;
    trouble = '';
    people = [];
    vacancies = [];
    refresh(id);
    loadPeople(id);
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
    <Avatar icon="domain" />

    <div>
      <div class="cnt-det-name" class:muted={!card.name}>{card.name || '— без названия —'}</div>

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
          Слить с другой компанией
        </button>
        {#if card.blacklist_value}
          <button
            class="menu-item"
            type="button"
            onclick={() => {
              close();
              unblock();
            }}
          >
            <span class="material-symbols-outlined">restart_alt</span>
            Убрать из blacklist
          </button>
        {:else}
          <button
            class="menu-item"
            type="button"
            onclick={() => {
              close();
              block();
            }}
          >
            <span class="material-symbols-outlined">block</span>
            Добавить в blacklist
          </button>
        {/if}

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
    <input class="cnt-input" maxlength="120" value={card.name} placeholder="Название" onchange={rename} />
    <input
      class="cnt-input"
      maxlength="200"
      value={card.website ?? ''}
      placeholder="Сайт / домен"
      onchange={(event) => save({ website: event.currentTarget.value.trim() })}
    />
  </div>

  <!-- Написания: под ними компания приходит в объявлениях. Потеряй карточка
       одно из них — следующая вакансия завела бы компанию заново. -->
  <div class="cnt-det-section">
    <ChipList
      items={card.aliases}
      onadd={(one) => save({ aliases: [...card.aliases, one] })}
      onremove={(index) => save({ aliases: card.aliases.filter((_, at) => at !== index) })}
    />
  </div>

  <div class="cnt-det-section">
    {#key companyId}
      <NotesField
        value={card.notes}
        placeholder="Заметки о компании…"
        delay={NOTES_DELAY}
        limit={2000}
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

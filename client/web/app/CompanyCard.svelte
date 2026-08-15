<script>
  // Карточка компании: её числа, поля и действия над ней.
  //
  // Открывается поверх списка: компанию правят, глядя на её же вакансии и
  // людей, и уводить ради этого с экрана значило бы терять из виду соседей по
  // списку.

  import CardDialog from '$components/CardDialog.svelte';
  import ChipList from '$components/ChipList.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { companyCandidate, companyLine } from '$state/companies.js';
  import { personName } from '$state/contacts.js';
  import { plural } from '$state/words.js';

  let { ask, say, companyId, onclose, onchanged } = $props();

  let card = $state(null);
  let people = $state([]);
  let vacancies = $state([]);
  let trouble = $state('');
  let asking = $state(null);
  let chosen = $state(null);

  let alive = true;

  const shown = $derived(card ? companyLine({ ...card, id: card.company_id }) : null);
  const chosenName = $derived(chosen ? companyLine(chosen).name : '');

  async function refresh() {
    const now = await ask('companies.detail', companyId);
    if (!alive) return;
    // Отказ не должен запирать окно на «Загрузка…»: человеку нужно хотя бы
    // выйти из него, а плашку он уже увидел.
    if (now === null) return (trouble = 'Не удалось прочитать компанию');
    card = now;
  }

  async function loadPeople() {
    const now = await ask('companies.people', companyId);
    if (now === null || !alive) return;
    people = now.hrs;
  }

  async function loadVacancies() {
    const now = await ask('companies.vacancies', { company_id: companyId });
    if (now === null || !alive) return;
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
    await refresh();
    if (done !== null) onchanged();
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
    await refresh();
    onchanged();
  }

  async function unblock() {
    const done = await ask('companies.unblock', companyId);
    if (done === null) return;
    say(done.updated ? 'Убрана из отсева' : 'В отсеве её не было');
    await refresh();
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
    refresh();
    loadPeople();
    loadVacancies();
    return () => {
      alive = false;
    };
  });
</script>

<CardDialog {trouble} ready={!!card} {onclose}>
  <div class="modal-title card-head">
    <span class="avatar avatar-empty material-symbols-outlined">domain</span>
    <span class="card-name">{shown.name}</span>
    {#if card.blacklist_value}<span class="kind-tag" data-kind="company">в отсеве</span>{/if}
  </div>

  <div class="card-meta">
    <span class="card-meta-item">
      <span class="material-symbols-outlined">work</span>
      {card.vacancy_count} {plural(card.vacancy_count, 'вакансия', 'вакансии', 'вакансий')}
    </span>
    <span class="card-meta-item">
      <span class="material-symbols-outlined">person</span>
      {card.hr_count} {plural(card.hr_count, 'человек', 'человека', 'человек')}
    </span>
  </div>

  <div class="form-grid">
    <input class="input" value={card.name} placeholder="Название" onchange={rename} />
    <input
      class="input"
      value={card.website ?? ''}
      placeholder="Сайт или домен"
      onchange={(event) => save({ website: event.currentTarget.value.trim() })}
    />
  </div>

  <!-- Написания: под ними компания приходит в объявлениях. Потеряй карточка
       одно из них — следующая вакансия завела бы компанию заново. -->
  <ChipList
    items={card.aliases}
    onadd={(one) => save({ aliases: [...card.aliases, one] })}
    onremove={(index) => save({ aliases: card.aliases.filter((_, at) => at !== index) })}
  />

  <textarea
    class="textarea"
    placeholder="Заметки о компании"
    value={card.notes ?? ''}
    onchange={(event) => save({ notes: event.currentTarget.value })}
  ></textarea>

  <div class="card-people">
    {#if !people.length}
      <div class="empty-note">Людей из этой компании ещё нет</div>
    {:else}
      {#each people as one (one.id)}
        <div class="stat-line">
          <span class="stat-name">{personName(one)}</span>
          <span class="stat-value">{one.vacancy_count}</span>
        </div>
      {/each}
    {/if}
  </div>

  <MiniVacancies {vacancies} empty="Вакансий этой компании ещё нет" />

  <div class="modal-actions card-actions">
    <button class="btn" type="button" onclick={() => (asking = 'merge')}>
      <span class="material-symbols-outlined">merge</span>
      Слить с другой
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

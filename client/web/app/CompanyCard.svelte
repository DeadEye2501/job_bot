<script>
  // Карточка компании: её числа, поля и действия над ней.
  //
  // Открывается поверх списка: компанию правят, глядя на её же вакансии и
  // людей, и уводить ради этого с экрана значило бы терять из виду соседей по
  // списку.

  import ChipList from '$components/ChipList.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import { companyLine } from '$state/companies.js';
  import { personName } from '$state/contacts.js';
  import { plural } from '$state/words.js';

  import CompanyMerge from './CompanyMerge.svelte';

  let { ask, say, companyId, onclose, onchanged } = $props();

  let card = $state(null);
  let people = $state([]);
  let vacancies = $state([]);
  let trouble = $state('');
  let asking = $state(null);

  let alive = true;

  const shown = $derived(card ? companyLine({ ...card, id: card.company_id }) : null);

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

  function merged() {
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

<div class="modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && onclose()}>
  <div class="modal-dialog card-dialog" role="dialog" aria-modal="true">
    {#if trouble}
      <div class="empty-note">{trouble}</div>
      <div class="modal-actions">
        <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
      </div>
    {:else if !card}
      <div class="empty-note">Загрузка…</div>
    {:else}
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

      <div class="card-vacancies">
        {#if !vacancies.length}
          <div class="empty-note">Вакансий этой компании ещё нет</div>
        {:else}
          {#each vacancies as one (one.id)}
            <div class="stat-line">
              <span class="stat-name">{one.title || 'Без названия'}</span>
              <span class="stat-value">
                <span class="status-dot" data-status={one.status}></span>
                {one.score ?? '—'}
              </span>
            </div>
          {/each}
        {/if}
      </div>

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
    {/if}
  </div>
</div>

{#if asking === 'delete'}
  <ConfirmDialog
    message={`Удалить компанию «${shown.name}»?\n\nСобранные вакансии останутся, но без компании. Откатить нельзя.`}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = null)}
  />
{/if}

{#if asking === 'merge'}
  <CompanyMerge
    {ask}
    absorbedId={companyId}
    absorbedName={shown.name}
    onclose={() => (asking = null)}
    onmerged={merged}
  />
{/if}

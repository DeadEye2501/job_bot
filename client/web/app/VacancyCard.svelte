<script>
  // Карточка вакансии: чем она оказалась, что с ней делали и на чём стоит
  // сейчас.
  //
  // Открывается поверх списка: вакансию читают, не теряя из виду соседние, —
  // рядом с ними и решают, стоит ли она отклика.

  import CardDialog from '$components/CardDialog.svelte';
  import StatusPicker from '$components/StatusPicker.svelte';
  import VacancyTimeline from '$components/VacancyTimeline.svelte';
  import { attempts } from '$state/attempts.js';
  import { gradeLabel, scoreTone } from '$state/vacancies.js';
  import { timelineRows } from '$state/vacancy_card.js';

  let { ask, say, vacancyId, onclose, onchanged } = $props();

  let card = $state(null);
  let notes = $state('');
  let trouble = $state('');
  let picking = $state(false);
  let saving = $state(false);

  const tries = attempts();
  let alive = true;

  const rows = $derived(card ? timelineRows(card.history, card.events) : []);
  const tone = $derived(card ? scoreTone(card.score, card.score_threshold) : '');

  /** Перечитать карточку целиком.
   *
   * Свой счёт попыток: правка пояснения и смена статуса перечитывают её каждая,
   * и ответы возвращаются вразнобой — лёгший поверх свежего старый показал бы
   * ленту без только что сделанного перехода.
   */
  async function refresh() {
    const mine = tries.next();
    const now = await ask('vacancies.detail', vacancyId);
    if (!alive || tries.stale(mine)) return;
    // Отказ не должен запирать окно на «Загрузка…»: человеку нужно хотя бы
    // выйти из него, а плашку он уже увидел.
    if (now === null) return (trouble = 'Не удалось прочитать вакансию');
    trouble = '';
    card = now.vacancy;
    notes = card.notes ?? '';
  }

  /** Записать заметку и показать то, что легло на самом деле.
   *
   * Перечитываем и после отказа: мост сводит пробельную заметку к пустоте, а
   * отклонённая правка осталась бы на экране — человек читал бы своё, а в базе
   * лежало бы прежнее.
   */
  async function saveNotes() {
    await ask('vacancies.save_notes', { vacancy_id: vacancyId, notes });
    return refresh();
  }

  /** Записать пояснение к переходу.
   *
   * Перечитываем всегда по тому же доводу, что и заметку: мост дописывает
   * точку, и записанное отличается от набранного, а отказ оставил бы
   * отклонённое на экране.
   */
  async function saveNote(historyId, text) {
    await ask('vacancies.save_history_explanation', {
      vacancy_id: vacancyId,
      history_id: historyId,
      explanation: text,
    });
    return refresh();
  }

  async function apply(status, explanation) {
    const was = card.status;
    saving = true;
    const done = await ask('vacancies.change_status', {
      vacancy_id: vacancyId,
      status,
      explanation,
    });
    if (!alive) return;
    saving = false;
    // Отказ окно выбора не закрывает: статус выбран, причина набрана, и
    // закрытие заставило бы набирать всё заново.
    if (done === null) return;
    picking = false;
    // Про переход говорим только когда он был: мост принимает и «тот же самый
    // статус с причиной», и объявлять это переходом значило бы врать.
    if (status !== was) say(`Статус: ${status}`);
    await refresh();
    onchanged();
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

<CardDialog {trouble} ready={!!card} {onclose}>
  <div class="modal-title vac-card-head">
    <div class="status-wrap">
      <button class="status-badge" type="button" onclick={() => (picking = !picking)}>
        <span class="status-dot" data-status={card.status}></span>
        <span class="status-label">{card.status}</span>
        <span class="material-symbols-outlined">expand_more</span>
      </button>
      {#if picking}
        <StatusPicker
          status={card.status}
          {saving}
          onapply={apply}
          oncancel={() => (picking = false)}
        />
      {/if}
    </div>
    <span class="card-name">{card.title || 'Без названия'}</span>
  </div>

  <div class="vac-chips">
    {#if card.score !== null}
      <span class="info-chip score" data-tone={tone}>{card.score}</span>
    {/if}
    <span class="info-chip">{gradeLabel(card.grade)}</span>
    {#if card.salary}<span class="info-chip">{card.salary}</span>{/if}
    {#if card.remote}<span class="info-chip">{card.remote}</span>{/if}
    {#if card.location}<span class="info-chip">{card.location}</span>{/if}
    {#if card.channel_username}
      <span class="info-chip">@{card.channel_username}</span>
    {/if}
  </div>

  <!-- Совпавшее с анкетой подсвечено: по нему видно, чем вакансия набрала свою
       оценку. -->
  {#if card.stack.length}
    <div class="vac-card-stack">
      <!-- Ключ по месту, а не по названию: разбор кладёт в стек то, что нашёл,
           и одно и то же название приходит дважды. -->
      {#each card.stack as one, at (at)}
        <span class="mini-chip" class:matched={one.matched}>{one.name}</span>
      {/each}
    </div>
  {/if}

  {#if card.description}
    <p class="vac-text">{card.description}</p>
  {/if}

  <div class="vac-contacts">
    <span class="card-meta-item">
      <span class="material-symbols-outlined">person</span>
      {#if card.hr}
        {card.hr.name || 'Без имени'}{#if card.hr.telegram_username}
          <span class="vac-dim">@{card.hr.telegram_username}</span>
        {/if}
      {:else}
        <span class="vac-dim">HR не определён</span>
      {/if}
    </span>
    <span class="card-meta-item">
      <span class="material-symbols-outlined">domain</span>
      {#if card.company_name}
        {card.company_name}
      {:else}
        <span class="vac-dim">Компания не определена</span>
      {/if}
    </span>
  </div>

  <textarea
    class="textarea"
    placeholder="Заметки по вакансии"
    bind:value={notes}
    onchange={saveNotes}
  ></textarea>

  <VacancyTimeline {rows} onsave={saveNote} />

  <div class="modal-actions card-actions">
    <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
  </div>
</CardDialog>

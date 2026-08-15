<script>
  // Карточка вакансии: чем она оказалась, что с ней делали и на чём стоит
  // сейчас.
  //
  // Открывается поверх списка: вакансию читают, не теряя из виду соседние, —
  // рядом с ними и решают, стоит ли она отклика.

  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import RawTextDialog from '$components/RawTextDialog.svelte';
  import StatusPicker from '$components/StatusPicker.svelte';
  import VacancyActions from '$components/VacancyActions.svelte';
  import VacancyTimeline from '$components/VacancyTimeline.svelte';
  import { attempts } from '$state/attempts.js';
  import { actionBlocks, rawNote } from '$state/vacancy_actions.js';
  import { gradeLabel, scoreTone } from '$state/vacancies.js';
  import { timelineRows } from '$state/vacancy_card.js';

  import VacancyLinks from './VacancyLinks.svelte';

  let { ask, say, events, lockedTip, vacancyId, onclose, onchanged } = $props();

  let card = $state(null);
  let notes = $state('');
  let trouble = $state('');
  let picking = $state(false);
  let saving = $state(false);
  let asking = $state(null);
  let linking = $state(null);
  let raw = $state(false);
  let sending = $state(false);

  const tries = attempts();
  let alive = true;

  const rows = $derived(card ? timelineRows(card.history, card.events) : []);
  const tone = $derived(card ? scoreTone(card.score, card.score_threshold) : '');
  const blocks = $derived(card ? actionBlocks(card, lockedTip) : { send: '', rerun: '' });

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

  /** Разобрать объявление заново.
   *
   * Ответ приходит сразу, а работа идёт дальше в боте: он занимает общий слот
   * обхода, и о ходе рассказывает нижняя полоса окна. Готовое приезжает вестью
   * о смене списка — по ней карточка и перечитывается.
   */
  async function rerun() {
    const done = await ask('vacancies.rerun', { vacancy_id: vacancyId });
    if (done === null) return;
    say('Разбор запущен');
  }

  /** Отправить отклик.
   *
   * Заперто на время полёта: заслон «уже откликались» стоит на мосту и читает
   * статус до отправки, а зов идёт своим чередом — два нажатия послали бы
   * человеку два письма. Перечитываем и после отказа: половина отказов
   * приходит оттого, что статус успел уехать, и на экране он уже другой.
   */
  async function send() {
    if (sending) return;
    asking = null;
    sending = true;
    const done = await ask('vacancies.send_application', { vacancy_id: vacancyId });
    if (!alive) return;
    sending = false;
    if (done !== null) say('Отклик отправлен');
    await refresh();
    onchanged();
  }

  async function drop() {
    asking = null;
    const done = await ask('vacancies.delete', { vacancy_id: vacancyId });
    if (done === null) return;
    say('Вакансия удалена');
    onchanged();
    onclose();
  }

  /** Открыть объявление в Telegram.
   *
   * Открывает его система, а не страница: адрес ведёт наружу, и окно раздаёт
   * свою папку, а не интернет. Ссылки может не быть вовсе — источник её не
   * прислал, — и тогда открывать нечего, о чём и говорим.
   */
  function source() {
    if (!card.source_url) return say('Ссылки на объявление нет');
    return ask('system.open_url', card.source_url);
  }

  /** Положить исходный текст в буфер обмена.
   *
   * Кладёт страница сама: мосту для этого делать нечего, а в окне буфер обмена
   * есть. Отказать он может — окно без разрешения на буфер такое бывает, — и
   * молчать об этом нельзя: человек уйдёт вставлять пустоту.
   */
  async function copyRaw() {
    if (!card.raw_text) return say('Копировать нечего');
    try {
      await navigator.clipboard.writeText(card.raw_text);
    } catch (trouble) {
      return say(`Не удалось скопировать: ${trouble}`);
    }
    say('Текст скопирован');
  }

  $effect(() => {
    alive = true;
    // Вакансию двигает не только это окно: бот разбирает её заново по нашей же
    // просьбе и правит статус по переписке. Весть о смене списка — то же
    // событие, по которому обновляется список под карточкой.
    const deaf = events.on('vacancies_list_changed', refresh);
    refresh();
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

{#if trouble}
  <div class="vac-detail-empty">{trouble}</div>
{:else if !card}
  <div class="vac-detail-empty">Загрузка…</div>
{:else}
  <div class="modal-title vac-card-head">
    <div class="pop-wrap">
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

    <VacancyActions
      {blocks}
      {say}
      onsend={() => (asking = 'send')}
      onrerun={rerun}
      onlinkhr={() => (linking = 'hr')}
      onlinkcompany={() => (linking = 'company')}
      onraw={() => (raw = true)}
      onsource={source}
      ondelete={() => (asking = 'delete')}
    />
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
{/if}

{#if asking === 'send'}
  <ConfirmDialog
    message={`Сочинить сопроводительное письмо и отправить его${card.hr?.name ? ` ${card.hr.name}` : ''} вместе с резюме?`}
    confirmLabel="Отправить"
    onconfirm={send}
    oncancel={() => (asking = null)}
  />
{/if}

{#if asking === 'delete'}
  <ConfirmDialog
    message={'Удалить эту вакансию?\n\nИстория статусов и события разбора уйдут вместе с ней. Переписка с HR останется. Откатить нельзя.'}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = null)}
  />
{/if}

{#if raw}
  <RawTextDialog
    note={rawNote(card)}
    text={card.raw_text ?? 'Исходный текст не сохранён'}
    oncopy={copyRaw}
    onclose={() => (raw = false)}
  />
{/if}

{#if linking !== null}
  <VacancyLinks
    {ask}
    {say}
    {vacancyId}
    kind={linking}
    onclose={() => (linking = null)}
    onlinked={() => {
      refresh();
      onchanged();
    }}
  />
{/if}

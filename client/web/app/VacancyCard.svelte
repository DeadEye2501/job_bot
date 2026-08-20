<script>
  // Карточка вакансии: чем она оказалась, что с ней делали и на чём стоит
  // сейчас.
  //
  // Стоит правой панелью рядом со списком: вакансию читают, не теряя из виду
  // соседние, — рядом с ними и решают, стоит ли она отклика.

  import Avatar from '$components/Avatar.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import NotesField from '$components/NotesField.svelte';
  import RawTextDialog from '$components/RawTextDialog.svelte';
  import StatusPicker from '$components/StatusPicker.svelte';
  import VacancyActions from '$components/VacancyActions.svelte';
  import VacancyTimeline from '$components/VacancyTimeline.svelte';
  import { living } from '$state/alive.js';
  import { attempts } from '$state/attempts.js';
  import { cardLinks } from '$state/card_links.js';
  import { actionBlocks, rawChips } from '$state/vacancy_actions.js';
  import { ago, gradeLabel, remoteLabel, scoreTone } from '$state/vacancies.js';
  import { timelineRows } from '$state/vacancy_card.js';

  import VacancyLinks from './VacancyLinks.svelte';

  // Пауза перед записью заметки. Столько же ждало прежнее окно: короче — и
  // мост получает вопрос на каждое слово, длиннее — и человек успевает уйти,
  // не увидев подтверждения.
  const NOTES_DELAY = 800;

  let { ask, say, events, lockedTip, vacancyId, oncontacts, onclose, onchanged } = $props();

  let card = $state(null);
  let picking = $state(false);
  // Обёртка пилюли и окошка статуса: по ней окошко считает «нажали мимо».
  // Своим узлом ему годится только она — кнопка лежит рядом с ним, не внутри.
  let statusWrap = $state(null);
  let saving = $state(false);
  let asking = $state(null);
  let linking = $state(null);
  let raw = $state(false);

  const tries = attempts();
  const alive = living();

  const rows = $derived(card ? timelineRows(card.history, card.events) : []);
  const tone = $derived(card ? scoreTone(card.score, card.score_threshold) : '');
  const blocks = $derived(card ? actionBlocks(card, lockedTip) : { send: '', rerun: '', source: '' });
  const links = $derived(card ? cardLinks(card) : null);
  // Когда объявление вышло: у поста есть своя метка, а у записи — только время
  // её заведения, и второе на день-другой позже первого.
  const posted = $derived(card ? card.posted_at || card.created_at : null);

  /** Перечитать карточку целиком.
   *
   * Свой счёт попыток: правка пояснения и смена статуса перечитывают её каждая,
   * и ответы возвращаются вразнобой — лёгший поверх свежего старый показал бы
   * ленту без только что сделанного перехода.
   *
   */
  async function refresh() {
    const mine = tries.next();
    const now = await ask('vacancies.detail', vacancyId);
    if (!alive.now || tries.stale(mine) || now === null) return;
    card = now.vacancy;
  }

  /** Записать заметку и вернуть то, что легло в базу.
   *
   * Карточку не перечитываем: человек мог набрать ещё, пока летел вопрос, и
   * пришедшее из базы стёрло бы это.
   */
  async function saveNotes(id, text) {
    const done = await ask('vacancies.save_notes', { vacancy_id: id, notes: text });
    if (!alive.now || done === null) return null;
    return done.notes ?? '';
  }

  /** Записать пояснение к переходу.
   *
   * Перечитываем карточку: мост дописывает точку, и записанное отличается от
   * набранного. Ответ говорит ленте, вспыхнуть ли зелёным.
   */
  async function saveNote(id, historyId, text) {
    const done = await ask('vacancies.save_history_explanation', {
      vacancy_id: id,
      history_id: historyId,
      explanation: text,
    });
    if (done === null) return false;
    await refresh();
    return true;
  }

  async function apply(status, explanation) {
    const was = card.status;
    saving = true;
    const done = await ask('vacancies.change_status', {
      vacancy_id: vacancyId,
      status,
      explanation,
    });
    if (!alive.now) return;
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
   * Ответа об отправке здесь не ждут: письмо сочиняет модель, и ждать её
   * значило бы держать окно. Ушло письмо или нет, скажет оболочка — вестью об
   * исходе, — а карточка перечитается по вести о смене списка.
   */
  async function send() {
    asking = null;
    const done = await ask('vacancies.send_application', { vacancy_id: vacancyId });
    if (done === null) return;
    say('Отклик отправляется');
  }

  async function drop() {
    asking = null;
    const done = await ask('vacancies.delete', { vacancy_id: vacancyId });
    if (done === null) return;
    say('Вакансия удалена');
    onchanged();
    onclose();
  }

  /** Открыть адрес наружу.
   *
   * Открывает его система, а не страница: адреса ведут в Telegram и на сайт
   * компании, а окно раздаёт свою папку, а не интернет.
   */
  function outside(url) {
    return ask('system.open_url', url);
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
    const settled = alive.mounted();
    // Перешли к другой вакансии — прежнюю с глаз долой, не дожидаясь ответа:
    // поле заметки берёт значение один раз, при заведении, и заведённое над
    // прежней карточкой держало бы чужую заметку до самого закрытия. Вести о
    // смене списка сюда не заходят — там вакансия та же, и гасить её нечему.
    card = null;
    // Вакансию двигает не только это окно: бот разбирает её заново по нашей же
    // просьбе и правит статус по переписке. Весть о смене списка — то же
    // событие, по которому обновляется список под карточкой.
    const deaf = events.on('vacancies_list_changed', refresh);
    refresh();
    return () => {
      settled();
      deaf();
    };
  });
</script>

{#if !card}
  <div class="vac-detail-empty">Загрузка…</div>
{:else}
  <div class="det-head">
    <div class="status-wrap" class:popover-open={picking} bind:this={statusWrap}>
      <button class="status-badge" type="button" onclick={() => (picking = !picking)}>
        <span class="status-dot" data-status={card.status}></span>
        <span class="status-label">{card.status}</span>
        <span class="material-symbols-outlined">expand_more</span>
      </button>
      {#if picking}
        <StatusPicker
          status={card.status}
          {saving}
          wrap={statusWrap}
          onapply={apply}
          oncancel={() => (picking = false)}
        />
      {/if}
    </div>
    <div class="det-title">{card.title || '—'}</div>

    <VacancyActions
      {blocks}
      {say}
      onsend={() => (asking = 'send')}
      onrerun={rerun}
      onlinkhr={() => (linking = { kind: 'hr', prefill: '' })}
      onlinkcompany={() => (linking = { kind: 'company', prefill: '' })}
      onraw={() => (raw = true)}
      onsource={() => outside(card.source_url)}
      ondelete={() => (asking = 'delete')}
    />
  </div>

  <div class="det-info">
    {#if card.score !== null}
      <span class="info-chip score" data-tone={tone}>Score: {card.score}</span>
    {/if}
    {#if card.grade}<span class="info-chip">{gradeLabel(card.grade)}</span>{/if}
    {#if card.salary}<span class="info-chip">{card.salary}</span>{/if}
    {#if card.remote}<span class="info-chip">{remoteLabel(card.remote)}</span>{/if}
    {#if card.location}<span class="info-chip">{card.location}</span>{/if}
    {#if card.channel_username}
      <button
        class="info-chip"
        class:linkable={card.source_url}
        type="button"
        title="Перейти к посту в канале"
        disabled={!card.source_url}
        onclick={() => outside(card.source_url)}
      >
        <span class="material-symbols-outlined">tag</span>{card.channel_username}
      </button>
    {/if}
    {#if posted}
      <span class="info-chip" title={posted}>
        <span class="material-symbols-outlined">schedule</span>{ago(posted, new Date())}
      </span>
    {/if}
  </div>

  <!-- Совпавшее с анкетой подсвечено: по нему видно, чем вакансия набрала свою
       оценку. -->
  {#if card.stack.length}
    <div class="det-section">
      <div class="det-stack">
        <!-- Ключ по месту, а не по названию: разбор кладёт в стек то, что
             нашёл, и одно и то же название приходит дважды. -->
        {#each card.stack as one, at (at)}
          <span class="stack-chip" class:matched={one.matched}>{one.name}</span>
        {/each}
      </div>
    </div>
  {/if}

  {#if card.description}
    <div class="det-section"><p>{card.description}</p></div>
  {/if}

  <div class="det-section">
    <div class="vac-contacts">
      <div class="contact-block">
        <Avatar avatar={card.hr?.avatar} name={card.hr?.name} icon="person" />
        <div class="hr-info">
          {#if !card.hr}
            <div class="hr-name muted">HR не определён</div>
          {:else}
            <button
              class="hr-name is-link"
              type="button"
              title="Открыть в Контактах"
              onclick={() => oncontacts(links.hrCard)}
            >
              {card.hr.name || '—'}
            </button>
          {/if}
        </div>
      </div>

      <div class="contact-block">
        <Avatar icon="domain" />
        <div class="hr-info">
          {#if !card.company_name}
            <div class="hr-name muted">Компания не определена</div>
          {:else if links.companyCard}
            <button
              class="hr-name is-link"
              type="button"
              title="Открыть в Контактах"
              onclick={() => oncontacts(links.companyCard)}
            >
              {card.company_name}
            </button>
          {:else}
            <!-- Имя разбор узнал, а связи нет: нажатие открывает подборщик с
                 этим самым именем, вместо того чтобы набирать его руками. -->
            <button
              class="hr-name is-link"
              type="button"
              title="Связать с компанией"
              onclick={() => (linking = { kind: 'company', prefill: links.companyPick })}
            >
              {card.company_name}
            </button>
          {/if}
        </div>
      </div>
    </div>
  </div>

  <div class="det-section">
    <!-- Своя запись на каждую вакансию: поле запечатывает номер при заведении,
         и заводиться заново на каждую его заставляет именно `{#key}` — без
         него запечатанный номер протухнет. -->
    {#key vacancyId}
      <NotesField
        value={card.notes}
        placeholder="Заметки по вакансии…"
        delay={NOTES_DELAY}
        owner={vacancyId}
        save={saveNotes}
      />
    {/key}
  </div>

  {#if rows.length}
    <div class="det-section">
      <!-- Своя лента на каждую вакансию: почему — сказано в её шапке. -->
      {#key vacancyId}
        <VacancyTimeline {rows} {vacancyId} onsave={saveNote} />
      {/key}
    </div>
  {/if}
{/if}

{#if asking === 'send'}
  <ConfirmDialog
    message="Сгенерировать сопроводительное письмо и отправить связанному HR с прикреплённым резюме?"
    confirmLabel="Отправить"
    onconfirm={send}
    oncancel={() => (asking = null)}
  />
{/if}

{#if asking === 'delete'}
  <ConfirmDialog
    message="Удалить эту вакансию? Связанная история статусов и события будут удалены."
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = null)}
  />
{/if}

{#if raw}
  <RawTextDialog
    id={card.id}
    chips={rawChips(card)}
    text={card.raw_text ?? ''}
    oncopy={copyRaw}
    onclose={() => (raw = false)}
  />
{/if}

{#if linking !== null}
  <VacancyLinks
    {ask}
    {say}
    {vacancyId}
    kind={linking.kind}
    prefill={linking.prefill}
    current={linking.kind === 'hr' ? (card.hr?.id ?? null) : card.company_id}
    onclose={() => (linking = null)}
    onlinked={() => {
      refresh();
      onchanged();
    }}
  />
{/if}

<script>
  // Карточка вакансии: чем она оказалась, что с ней делали и на чём стоит
  // сейчас.
  //
  // Стоит правой панелью рядом со списком: вакансию читают, не теряя из виду
  // соседние, — рядом с ними и решают, стоит ли она отклика.

  import ApplyWaysDialog from '$components/ApplyWaysDialog.svelte';
  import Avatar from '$components/Avatar.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import NotesField from '$components/NotesField.svelte';
  import RawTextDialog from '$components/RawTextDialog.svelte';
  import ScreeningDialog from '$components/ScreeningDialog.svelte';
  import StatusPicker from '$components/StatusPicker.svelte';
  import VacancyActions from '$components/VacancyActions.svelte';
  import VacancyTimeline from '$components/VacancyTimeline.svelte';
  import { living } from '$state/alive.js';
  import { cardFinish } from '$state/card_finish.js';
  import { cardLinks } from '$state/card_links.js';
  import { miniRead } from '$state/mini_read.js';
  import { round } from '$state/round.svelte.js';
  import {
    actionBlocks,
    applyChoices,
    noChoiceReason,
    rawChips,
    sourcePill,
  } from '$state/vacancy_actions.js';
  import { ago, gradeLabel, remoteLabel, salaryLabel, scoreTone } from '$state/vacancies.js';
  import { timelineRows } from '$state/vacancy_card.js';

  import VacancyContactsSection from './VacancyContactsSection.svelte';
  import VacancyLinks from './VacancyLinks.svelte';

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
  let choosing = $state(null);
  let screening = $state(null);

  const alive = living();

  const dropCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'vacancies.delete',
    note: 'Вакансия удалена',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const rows = $derived(card ? timelineRows(card.history, card.events) : []);
  const tone = $derived(card ? scoreTone(card.score, card.score_threshold) : '');
  const salary = $derived(card ? salaryLabel(card) : '');
  const source = $derived(card ? sourcePill(card) : null);
  const blocks = $derived(
    card ? actionBlocks(card, lockedTip, round.running) : { send: '', rerun: '', source: '', raw: '' },
  );
  const links = $derived(card ? cardLinks(card) : null);
  // Когда объявление вышло: у поста есть своя метка, а у записи — только время
  // её заведения, и второе на день-другой позже первого.
  const posted = $derived(card ? card.posted_at || card.created_at : null);

  /** Перечитать карточку целиком.
   *
   * Свой счёт попыток: правка пояснения и смена статуса перечитывают её каждая,
   * и ответы возвращаются вразнобой — лёгший поверх свежего старый показал бы
   * ленту без только что сделанного перехода.
   */
  const refresh = miniRead({
    ask: (method, payload) => ask(method, payload),
    alive: () => alive.now,
    method: 'vacancies.detail',
    payload: (id) => id,
    key: 'vacancy',
    show: (one) => (card = one),
  });

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
    await refresh(vacancyId);
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
    await refresh(vacancyId);
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

  /** Ответ моста о вакансии — или пусто, если открыта уже другая.
   *
   * Номер запечатан до вопроса: панель одна на весь список, и ответ о прежней
   * вакансии, пришедший уже к новой, лёг бы на неё — способы ушли бы откликом
   * по ней. Зов приходит готовым, с именем моста в нём: так его видит шов имён.
   */
  async function own(asked) {
    const id = vacancyId;
    const found = await asked(id);
    return alive.now && found !== null && id === vacancyId ? found : null;
  }

  /** Откликнуться: единственный способ уходит сразу, из нескольких выбирают в окне. */
  async function respond() {
    const found = await own((id) => ask('vacancies.apply_ways', id));
    if (found === null) return;
    const rows = applyChoices(found, card.hr);
    if (rows.length === 0) return say(noChoiceReason(found));
    if (rows.length === 1) return send(rows[0]);
    choosing = rows;
  }

  /** Отправить отклик выбранным способом.
   *
   * Ответа об отправке здесь не ждут: письмо сочиняет модель, и ждать её
   * значило бы держать окно. Ушло письмо или нет, скажет оболочка — вестью об
   * исходе, — а карточка перечитается по вести о смене списка.
   */
  async function send(row) {
    choosing = null;
    const done = row.way
      ? await ask('vacancies.apply_via', { vacancy_id: vacancyId, ...row.way })
      : await ask('vacancies.send_application', { vacancy_id: vacancyId });
    if (done === null) return;
    say('Отклик отправляется');
  }

  async function showScreening() {
    const found = await own((id) => ask('vacancies.screening', id));
    if (found !== null) screening = found.applications;
  }

  async function drop() {
    asking = null;
    await dropCard({ vacancy_id: vacancyId });
  }

  /** Открыть адрес наружу.
   *
   * Открывает его система, а не страница: адреса ведут в Telegram и на сайт
   * компании, а окно раздаёт свою папку, а не интернет.
   */
  function outside(url) {
    return ask('system.open_url', url);
  }

  /** Положить текст в буфер обмена и сказать об этом.
   *
   * Кладёт страница сама: мосту для этого делать нечего, а в окне буфер обмена
   * есть. Отказать он может — окно без разрешения на буфер такое бывает, — и
   * молчать об этом нельзя: человек уйдёт вставлять пустоту.
   */
  async function copy(text, done) {
    if (!text) return say('Копировать нечего');
    try {
      await navigator.clipboard.writeText(text);
    } catch (trouble) {
      return say(`Не удалось скопировать: ${trouble}`);
    }
    say(done);
  }

  $effect(() => {
    // Номер читается до захода, и это здесь несущее: сам заход читает вне
    // слежения, а панель одна на весь список — выбор другой строки меняет
    // компоненту свойство, не заводя его заново.
    const id = vacancyId;
    const settled = alive.entered(() => {
      // Перешли к другой вакансии — прежнюю с глаз долой, не дожидаясь ответа:
      // поле заметки берёт значение один раз, при заведении, и заведённое над
      // прежней карточкой держало бы чужую заметку до самого закрытия. Вести о
      // смене списка сюда не заходят — там вакансия та же, и гасить её нечему.
      card = null;
      refresh(id);
    });
    // Вакансию двигает не только это окно: бот разбирает её заново по нашей же
    // просьбе и правит статус по переписке. Весть о смене списка — то же
    // событие, по которому обновляется список под карточкой.
    const deaf = events.on('vacancies_list_changed', () => refresh(id));
    return () => {
      settled();
      deaf();
    };
  });
</script>

{#if !card}
  <div class="empty-note vac-detail-empty">Загрузка…</div>
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
    <button
      class="det-title"
      type="button"
      onclick={() => copy(card.title, 'Название скопировано')}
    >
      {card.title || '—'}
    </button>

    <VacancyActions
      {blocks}
      {say}
      onsend={respond}
      onrerun={rerun}
      onlinkhr={() => (linking = { kind: 'hr', prefill: '' })}
      onlinkcompany={() => (linking = { kind: 'company', prefill: '' })}
      onraw={() => (raw = true)}
      screened={card.has_screening}
      onscreening={showScreening}
      onsource={() => outside(card.source_url)}
      ondelete={() => (asking = 'delete')}
    />
  </div>

  <div class="det-info">
    {#if card.score !== null}
      <span class="info-chip score" data-tone={tone}>Score: {card.score}</span>
    {/if}
    {#if card.grade}<span class="info-chip">{gradeLabel(card.grade)}</span>{/if}
    {#if salary}<span class="info-chip">{salary}</span>{/if}
    {#if card.remote}<span class="info-chip">{remoteLabel(card.remote)}</span>{/if}
    {#if card.location}<span class="info-chip">{card.location}</span>{/if}
    {#if source}
      <button
        class="info-chip"
        class:linkable={card.source_url}
        type="button"
        title={source.title}
        disabled={!card.source_url}
        onclick={() => outside(card.source_url)}
      >
        <span class="material-symbols-outlined">{source.icon}</span>{source.text}
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
    <div class="card-section det-section">
      <div class="det-stack">
        <!-- Ключ по месту, а не по названию: разбор кладёт в стек то, что
             нашёл, и одно и то же название приходит дважды. -->
        {#each card.stack as one, at (at)}
          <span class="info-chip stack-chip" class:matched={one.matched}>{one.name}</span>
        {/each}
      </div>
    </div>
  {/if}

  {#if card.description}
    <div class="card-section det-section"><p>{card.description}</p></div>
  {/if}

  <div class="card-section det-section">
    <div class="vac-contacts">
      <div class="contact-block">
        <Avatar avatar={card.hr?.avatar} name={card.hr?.name} icon="person" />
        <div class="hr-info">
          {#if !card.hr}
            <div class="hr-name muted">HR не определён</div>
          {:else}
            <button
              class="hr-name link-hover"
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
              class="hr-name link-hover"
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
              class="hr-name link-hover"
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

  <div class="card-section det-section">
    <VacancyContactsSection
      {vacancyId}
      contacts={card.contacts}
      {ask}
      onopen={outside}
      onchanged={(contacts) => (card = { ...card, contacts })}
    />
  </div>

  <div class="card-section det-section">
    <!-- Своя запись на каждую вакансию: поле запечатывает номер при заведении,
         и заводиться заново на каждую его заставляет именно `{#key}` — без
         него запечатанный номер протухнет. -->
    {#key vacancyId}
      <NotesField
        value={card.notes}
        placeholder="Заметки по вакансии…"
        owner={vacancyId}
        save={saveNotes}
      />
    {/key}
  </div>

  {#if rows.length}
    <div class="card-section det-section">
      <!-- Своя лента на каждую вакансию: почему — сказано в её шапке. -->
      {#key vacancyId}
        <VacancyTimeline {rows} {vacancyId} onsave={saveNote} />
      {/key}
    </div>
  {/if}
{/if}

{#if choosing !== null}
  <ApplyWaysDialog
    rows={choosing}
    locked={blocks.send}
    onapply={send}
    onclose={() => (choosing = null)}
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
    oncopy={() => copy(card.raw_text, 'Текст скопирован')}
    onclose={() => (raw = false)}
  />
{/if}

{#if screening !== null}
  <ScreeningDialog applications={screening} onclose={() => (screening = null)} />
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
      refresh(vacancyId);
      onchanged();
    }}
  />
{/if}

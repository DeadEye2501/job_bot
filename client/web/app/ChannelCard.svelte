<script>
  // Карточка канала: его числа, воронка и вакансии, которые он принёс.
  //
  // Стоит правой панелью рядом со списком: канал правят, глядя на его же числа,
  // и уводить ради этого с экрана значило бы терять из виду соседей по списку.

  import ActionsMenu from '$components/ActionsMenu.svelte';
  import Avatar from '$components/Avatar.svelte';
  import BlacklistMenuItem from '$components/BlacklistMenuItem.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import { attempts } from '$state/attempts.js';
  import { channelName, channelStats, pollBlock, telegramHref } from '$state/contacts.js';
  import { PAGE, appended, refreshLimit } from '$state/paging.js';
  import { donut } from '$state/stats.js';

  let { ask, say, lockedTip, events, channelId, onvacancy, onclose, onchanged } = $props();

  let card = $state(null);
  let vacancies = $state([]);
  let hasMore = $state(false);
  let digging = $state(false);
  let asking = $state(false);
  let trouble = $state('');

  // Свой счёт попыток на каждый вопрос: панель живёт одна на всю вкладку, и
  // канал в ней переключают нажатием по соседней строке — ответ про прежний,
  // лёгший поверх свежего, показал бы его числа под новым именем.
  const cardTries = attempts();
  const vacancyTries = attempts();
  let alive = true;

  const shown = $derived(card ? channelName({ ...card, id: card.channel_id }) : null);
  const pollTip = $derived(pollBlock(card, lockedTip));
  const numbers = $derived(card ? channelStats(card.stats) : null);
  const funnel = $derived(card ? donut(card.stats.status_counts) : []);

  async function refresh(id) {
    const mine = cardTries.next();
    const now = await ask('channels.detail', id);
    if (!alive || cardTries.stale(mine)) return;
    // Отказ не должен запирать панель на «Загрузка…»: человеку нужно хотя бы
    // перейти к соседнему каналу, а плашку он уже увидел.
    if (now === null) return (trouble = 'Не удалось прочитать канал');
    card = now;
  }

  /** Дочитать вакансии канала.
   *
   * Страницами: каналов с тысячей вакансий хватает, и разом такой список не
   * рисуется. `append` — добор к показанному, `replace` — первая страница.
   *
   * Перечитывание берёт столько строк, сколько показано, а не страницу: весть
   * приходит на каждое разобранное объявление, и страницей она схлопывала бы
   * пролистанное снова и снова — ровно во время того прогона, который человек
   * и запустил.
   */
  async function loadVacancies(id, mode = 'replace') {
    const mine = vacancyTries.next();
    const page = await ask('channels.vacancies', {
      channel_id: id,
      limit: mode === 'append' ? PAGE : refreshLimit(vacancies.length),
      offset: mode === 'append' ? vacancies.length : 0,
      mode,
    });
    if (page === null || !alive || vacancyTries.stale(mine)) return;
    vacancies = mode === 'append' ? appended(vacancies, page.vacancies) : page.vacancies;
    hasMore = page.has_more;
  }

  /** Дочитать следующую страницу вакансий: панель подошла к концу.
   *
   * Зовёт список — прокручивается панель целиком, вместе с шапкой и числами, и
   * знает об этой прокрутке она.
   */
  export function more() {
    if (!hasMore || digging) return;
    digging = true;
    loadVacancies(channelId, 'append').finally(() => {
      digging = false;
    });
  }

  /** Опросить канал сейчас.
   *
   * Просьба уходит боту, а он при погасших лампах не поднят вовсе: пункт заперт
   * и объяснён теми же словами, что и кнопка обхода внизу окна.
   *
   * Ответа о прогоне здесь не ждут: на каждый новый пост уходит до пяти
   * обращений к модели. Чем кончилось, скажет оболочка вестью об исходе, а
   * числа карточки подтянутся вестью о смене списка вакансий.
   */
  async function pollNow() {
    const done = await ask('channels.poll_now', channelId);
    if (done === null) return;
    say('Прогон канала запущен');
  }

  async function resetCursor() {
    const done = await ask('channels.reset_cursor', channelId);
    if (done === null) return;
    say(
      'Отметка прочитанного сброшена — следующий обход перечитает последние посты канала ' +
        '(сколько именно, задаёт глубина добора)',
    );
  }

  /** Занести канал в отсев или убрать оттуда.
   *
   * Два зова, а не имя за условием: спрятанное в тернарий имя выпадает из шва
   * с мостом.
   */
  async function switchBlock() {
    const done = card.blacklist_value
      ? await ask('channels.unblock', channelId)
      : await ask('channels.block', channelId);
    if (done === null) return;
    await refresh(channelId);
    onchanged();
  }

  async function drop() {
    asking = false;
    const done = await ask('channels.delete', channelId);
    if (done === null) return;
    onchanged();
    onclose();
  }

  $effect(() => {
    alive = true;
    const id = channelId;
    // Показанное прежним каналом уходит сразу: панель одна, и его числа под
    // новым именем читались бы как числа нового.
    card = null;
    trouble = '';
    vacancies = [];
    hasMore = false;
    refresh(id);
    loadVacancies(id);
    // Канал приносит вакансии и во время прогона, и сам по себе обходом: его
    // числа и перечень стареют, пока карточка открыта, а прогнавший канал
    // человек смотрит именно на них.
    const deaf = events.on('vacancies_list_changed', () => {
      refresh(id);
      loadVacancies(id);
    });
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

{#if trouble}
  <div class="cnt-detail-empty">{trouble}</div>
{:else if !card}
  <div class="cnt-detail-empty">Загрузка…</div>
{:else}
  <div class="cnt-det-head">
    <Avatar avatar={card.avatar} icon="tag" />

    <div>
      <div class="cnt-det-name">{shown.name}</div>

      <div class="cnt-det-sub">
        {#if card.username}
          <button
            class="cnt-det-link"
            type="button"
            title="Открыть в Telegram"
            onclick={() => ask('system.open_url', telegramHref(card.username))}
          >
            @{card.username}
          </button>
        {:else}
          <span>@—</span>
        {/if}
      </div>

      {#if card.blacklist_value}
        <div class="cnt-det-meta-row">
          <span class="cnt-det-meta-chip blacklist" title="В blacklist: {card.blacklist_value}">
            <span class="material-symbols-outlined">block</span>
            В blacklist
          </span>
        </div>
      {/if}
    </div>

    <ActionsMenu>
      {#snippet children(close)}
        <button
          class="menu-item"
          type="button"
          disabled={!!pollTip}
          title={pollTip || 'Запустить поллинг этого канала'}
          onclick={() => {
            close();
            pollNow();
          }}
        >
          <span class="material-symbols-outlined">refresh</span>
          Прогнать сейчас
        </button>
        <button
          class="menu-item"
          type="button"
          title="Сбросить last_processed_msg_id"
          onclick={() => {
            close();
            resetCursor();
          }}
        >
          <span class="material-symbols-outlined">restart_alt</span>
          Сбросить курсор
        </button>
        <BlacklistMenuItem
          blocked={!!card.blacklist_value}
          {close}
          onblock={switchBlock}
          onunblock={switchBlock}
        />

        <div class="menu-line"></div>

        <button
          class="menu-item danger"
          type="button"
          onclick={() => {
            close();
            asking = true;
          }}
        >
          <span class="material-symbols-outlined">delete</span>
          Удалить канал
        </button>
      {/snippet}
    </ActionsMenu>
  </div>

  <div class="cnt-det-section">
    <div class="ch-stats-grid">
      <div class="ch-stat">
        <span class="big-num ch-stat-num">{card.stats.vacancies_per_day}</span>
        <span class="ch-stat-label">Вакансий в день</span>
      </div>
      <div class="ch-stat">
        <span class="big-num ch-stat-num fit">{numbers.fit}</span>
        <span class="ch-stat-label">Подходящих вакансий</span>
      </div>
      <div class="ch-stat">
        <span class="big-num ch-stat-num apply">{numbers.apply}</span>
        <span class="ch-stat-label">Откликов из подходящих</span>
      </div>
      <div class="ch-stat">
        <span class="big-num ch-stat-num response">{numbers.response}</span>
        <span class="ch-stat-label">Ответов на отклики</span>
      </div>
    </div>

    {#if numbers.empty}
      <div class="ch-stats-empty">Из этого канала ещё не пришло вакансий</div>
    {:else}
      <div class="ch-bar">
        {#each funnel as part (part.name)}
          <div
            class="ch-bar-seg"
            data-status={part.name}
            style="width: {part.percent}%"
            title="{part.name} {part.count}"
          ></div>
        {/each}
      </div>
      <!-- Легенда под полосой: одиннадцать цветов без подписей не читаются, а
           подписать отрезки внутри полосы негде. -->
      <div class="ch-bar-legend">
        {#each funnel as part (part.name)}
          <span class="legend-item">
            <span class="status-dot" data-status={part.name}></span>
            {part.name} {part.count}
          </span>
        {/each}
      </div>
    {/if}
  </div>

  <MiniVacancies
    {vacancies}
    empty="Из этого канала ещё нет вакансий."
    loading={digging}
    onpick={onvacancy}
  />
{/if}

{#if asking}
  <ConfirmDialog
    message={`Удалить «${shown.name}»?\n\nСвязанные вакансии останутся, но без привязки к каналу. Действие необратимо.`}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = false)}
  />
{/if}

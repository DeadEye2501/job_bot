<script>
  // Карточка канала: числа по нему и действия над ним.
  //
  // Открывается поверх списка: канал правят, глядя на его же числа, и уводить
  // ради этого с экрана значило бы терять из виду соседей по списку.

  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import DonutChart from '$components/DonutChart.svelte';
  import { channelName } from '$state/contacts.js';
  import { donut } from '$state/stats.js';

  let { ask, say, channelId, onclose, onchanged } = $props();

  const PAGE = 50;

  let card = $state(null);
  let vacancies = $state([]);
  let hasMore = $state(false);
  let asking = $state(null);
  let trouble = $state('');

  let alive = true;

  const statuses = $derived(donut(card?.stats.status_counts || {}));
  const shown = $derived(card ? channelName({ ...card, id: card.channel_id }) : null);

  async function refresh() {
    const now = await ask('channels.detail', channelId);
    if (!alive) return;
    // Отказ не должен запирать окно на «Загрузка…»: человеку нужно хотя бы
    // выйти из него, а плашку он уже увидел.
    if (now === null) return (trouble = 'Не удалось прочитать канал');
    card = now;
  }

  /** Дочитать вакансии канала.
   *
   * Страницами: каналов с тысячей вакансий хватает, и разом такой список не
   * рисуется. `append` — добор к показанному, `replace` — первая страница.
   */
  async function loadVacancies(mode = 'replace') {
    const page = await ask('channels.vacancies', {
      channel_id: channelId,
      limit: PAGE,
      offset: mode === 'append' ? vacancies.length : 0,
      mode,
    });
    if (page === null || !alive) return;
    vacancies = mode === 'append' ? [...vacancies, ...page.vacancies] : page.vacancies;
    hasMore = page.has_more;
  }

  async function pollNow() {
    const done = await ask('channels.poll_now', channelId);
    if (done === null) return;
    say('Канал опрашивается');
  }

  async function resetCursor() {
    asking = null;
    const done = await ask('channels.reset_cursor', channelId);
    if (done === null) return;
    say('Отметка прочитанного сброшена — следующий обход прочитает канал заново');
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
    await refresh();
    onchanged();
  }

  $effect(() => {
    alive = true;
    refresh();
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
        {#if card.avatar}
          <img class="avatar" src={card.avatar} alt="" />
        {:else}
          <span class="avatar avatar-empty material-symbols-outlined">campaign</span>
        {/if}
        <span class="card-name">{shown.name}</span>
        {#if shown.handle}<span class="card-handle">{shown.handle}</span>{/if}
        {#if card.blacklist_value}<span class="kind-tag" data-kind="channel">в отсеве</span>{/if}
      </div>

      <div class="status-card">
        <div class="stat-lines">
          <div class="stat-line">
            <span class="stat-name">Вакансий собрано</span>
            <span class="stat-value">{card.stats.total}</span>
          </div>
          <div class="stat-line">
            <span class="stat-name">В день</span>
            <span class="stat-value">{card.stats.vacancies_per_day ?? '—'}</span>
          </div>
          <div class="stat-line">
            <span class="stat-name">Годных</span>
            <span class="stat-value">{card.stats.fit_percent ?? '—'}%</span>
          </div>
          <div class="stat-line">
            <span class="stat-name">Откликов</span>
            <span class="stat-value">{card.stats.apply_percent ?? '—'}%</span>
          </div>
          <div class="stat-line">
            <span class="stat-name">Ответили</span>
            <span class="stat-value">{card.stats.response_percent ?? '—'}%</span>
          </div>
        </div>
        <!-- Легенда рядом с кольцом: одиннадцать цветов без подписей не
             читаются, а подписать сегменты внутри кольца негде. -->
        <div class="status-list">
          {#each statuses as one (one.name)}
            <div class="status-item">
              <span class="status-dot" data-status={one.name}></span>
              <span class="status-name">{one.name}</span>
              <span class="status-count">{one.count}</span>
            </div>
          {/each}
        </div>
        <DonutChart parts={statuses} total={card.stats.total} label="Всего" />
      </div>

      <div class="card-vacancies">
        {#if !vacancies.length}
          <div class="empty-note">С этого канала вакансий ещё нет</div>
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
          {#if hasMore}
            <button class="add-more" type="button" onclick={() => loadVacancies('append')}>
              Показать ещё
            </button>
          {/if}
        {/if}
      </div>

      <div class="modal-actions card-actions">
        <button class="btn" type="button" onclick={pollNow}>
          <span class="material-symbols-outlined">refresh</span>
          Опросить сейчас
        </button>
        <button class="btn" type="button" onclick={() => (asking = 'reset')}>
          <span class="material-symbols-outlined">restart_alt</span>
          Сбросить отметку
        </button>
        <button class="btn danger" type="button" onclick={switchBlock}>
          <span class="material-symbols-outlined">block</span>
          {card.blacklist_value ? 'Убрать из отсева' : 'В чёрный список'}
        </button>
        <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
      </div>
    {/if}
  </div>
</div>

{#if asking === 'reset'}
  <ConfirmDialog
    message={'Сбросить отметку прочитанного?\n\nСледующий обход прочитает канал с начала и заново разберёт всё, что там есть. Это долго и стоит вызовов модели.'}
    confirmLabel="Сбросить"
    onconfirm={resetCursor}
    oncancel={() => (asking = null)}
  />
{/if}

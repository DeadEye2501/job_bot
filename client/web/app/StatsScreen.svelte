<script>
  // Экран статистики: пять карточек за выбранный срок.
  //
  // Каждая карточка спрашивает своё: считаются они по-разному, и ждать самую
  // медленную ради самой быстрой незачем. Ответ, пришедший на прежний срок,
  // отбрасывается — иначе карточки показывали бы разные периоды разом.
  //
  // Зовы написаны литералами, а не собраны таблицей путей: имя, спрятанное в
  // таблицу, выпадает из шва с мостом — сторож ищет его на месте зова.

  import DonutChart from '$components/DonutChart.svelte';
  import StatsCard from '$components/StatsCard.svelte';
  import TopTabs from '$components/TopTabs.svelte';
  import { PERIODS, donut, duration, kpiRow, weekBars } from '$state/stats.js';

  let { ask } = $props();

  let period = $state('month');
  let kpi = $state(null);
  let breakdown = $state(null);
  let responses = $state(null);
  let skills = $state(null);
  let channels = $state(null);

  let alive = true;

  /** Спросить карточку и принять ответ, если он ещё нужен.
   *
   * Срок мог смениться, пока ответ шёл: чужие числа под новой подписью
   * читались бы как настоящие.
   */
  async function taken(asked, answer) {
    return answer !== null && alive && asked === period ? answer : null;
  }

  async function load() {
    const asked = period;
    kpi = breakdown = responses = skills = channels = null;
    ask('stats.kpi', asked).then(async (one) => (kpi = (await taken(asked, one)) ?? kpi));
    ask('stats.status_breakdown', asked).then(
      async (one) => (breakdown = (await taken(asked, one)) ?? breakdown),
    );
    ask('stats.hr_responses', asked).then(
      async (one) => (responses = (await taken(asked, one)) ?? responses),
    );
    ask('stats.skills', asked).then(async (one) => (skills = (await taken(asked, one)) ?? skills));
    ask('stats.channels_pipeline', asked).then(
      async (one) => (channels = (await taken(asked, one)) ?? channels),
    );
  }

  const statuses = $derived(donut(breakdown?.counts || {}));
  const shownTotal = $derived(statuses.reduce((sum, one) => sum + one.count, 0));
  const week = $derived(weekBars(responses?.by_weekday || [0, 0, 0, 0, 0, 0, 0]));

  $effect(() => {
    alive = true;
    // Читает `period` нарочно: сменился срок — эффект заводится заново и
    // перечитывает всё сам. Второй зов из обработчика вкладки удвоил бы
    // работу моста на каждое нажатие.
    period;
    load();
    return () => {
      alive = false;
    };
  });
</script>

<TopTabs
  tabs={PERIODS.map((one) => ({ key: one.key, label: one.label }))}
  active={period}
  onpick={(key) => (period = key)}
/>

<div class="screen-body">
  <div class="stats-grid">
    <StatsCard title="Показатели" ready={!!kpi} wide>
      <div class="kpi-row">
        {#each kpiRow(kpi, period) as one (one.key)}
          <div class="kpi">
            <span class="kpi-num" data-tone={one.tone}>{one.total}</span>
            <span class="kpi-label">{one.label}</span>
            {#if one.delta}
              <span class="kpi-delta" data-tone={one.delta.tone}>{one.delta.text}</span>
            {/if}
          </div>
        {/each}
      </div>
    </StatsCard>

    <StatsCard title="Статусы" ready={!!breakdown}>
      <div class="status-card">
        <div class="status-list">
          {#each statuses as one (one.name)}
            <div class="status-item">
              <span class="status-dot" data-status={one.name}></span>
              <span class="status-name">{one.name}</span>
              <span class="status-count">{one.count}</span>
            </div>
          {/each}
        </div>
        <DonutChart parts={statuses} total={shownTotal} label="Всего" />
      </div>
    </StatsCard>

    <StatsCard title="Ответы HR" ready={!!responses}>
      <div class="stat-lines">
        <div class="stat-line">
          <span class="stat-name">Медиана ответа</span>
          <span class="stat-value">{duration(responses.median_seconds)}</span>
        </div>
        <div class="stat-line">
          <span class="stat-name">Без ответа</span>
          <span class="stat-value">
            {responses.no_response_pct ?? '—'}% из {responses.applied_count}
          </span>
        </div>
      </div>

      <!-- Дни недели: по ним видно, когда людям писать. Столбцы читаются друг
           относительно друга, поэтому высота считается от самого высокого. -->
      <div class="week-bars">
        {#each week as one (one.label)}
          <div class="week-bar" title="{one.label}: {one.count}">
            <div class="week-fill" style="height: {one.percent}%"></div>
            <span class="week-label">{one.label}</span>
          </div>
        {/each}
      </div>
    </StatsCard>

    <StatsCard title="Навыки в вакансиях" ready={!!skills}>
      <div class="stat-lines">
        {#each skills.skills as one (one.label)}
          <div class="stat-line">
            <span class="stat-name" class:mine={one.mine}>{one.label}</span>
            <span class="stat-value">{one.count}</span>
          </div>
        {/each}
        {#if !skills.skills.length}
          <div class="empty-note">Ни один навык не встретился дважды</div>
        {/if}
      </div>
    </StatsCard>

    <StatsCard title="Каналы" ready={!!channels} wide>
      <table class="stats-table">
        <thead>
          <tr>
            <th>Канал</th>
            <th>Всего</th>
            <th>Мусор</th>
            <th>Не подходит</th>
            <th>Годных</th>
            <th>Откликов</th>
            <th>Ответили</th>
            <th>Позвали</th>
            <th>Отказ</th>
            <th>Ответ/отклик</th>
            <th>Зов/отклик</th>
          </tr>
        </thead>
        <tbody>
          {#each channels.channels as one (one.id)}
            <tr>
              <td class="stats-table-name">{one.label}</td>
              <td>{one.total}</td>
              <td>{one.trash}</td>
              <td>{one.not_fit}</td>
              <td>{one.fit}</td>
              <td>{one.sent}</td>
              <td>{one.answered}</td>
              <td>{one.invite_plus}</td>
              <td>{one.decline}</td>
              <td>{one.conv_answ_sent ?? '—'}%</td>
              <td>{one.conv_invite_sent ?? '—'}%</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if !channels.channels.length}
        <div class="empty-note">За этот срок каналы ничего не принесли</div>
      {/if}
    </StatsCard>
  </div>
</div>

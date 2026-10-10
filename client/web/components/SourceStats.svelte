<script>
  // Числа источника вакансий и его воронка: четыре числа и полоса положений
  // дел с легендой.
  //
  // Своим компонентом: так считают и канал, и агрегатор — оба источники, и
  // числа у них одни. `empty` — слово, когда считать ещё нечего: у канала и
  // агрегатора оно своё.
  import { sourceStats } from '$state/sources.js';
  import { donut } from '$state/stats.js';

  let { stats, empty } = $props();

  const numbers = $derived(sourceStats(stats));
  const funnel = $derived(donut(stats.status_counts));
</script>

<div class="card-section">
  <div class="ch-stats-grid">
    <div class="ch-stat">
      <span class="big-num ch-stat-num">{stats.vacancies_per_day}</span>
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
    <div class="ch-stats-empty">{empty}</div>
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

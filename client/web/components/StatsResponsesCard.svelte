<script>
  // Ответы HR: столбцы по дням недели и две метрики под ними.
  //
  // Пустых состояний своих нет: столбцы на нуле, дни недели и прочерки в
  // метриках сами говорят «откликов не было», а подменённая карточка
  // выглядела бы недогрузившейся.
  import { share } from '$state/sources.js';
  import { duration, weekBars } from '$state/stats.js';

  let { answer } = $props();

  const bars = $derived(weekBars(answer.by_weekday || [0, 0, 0, 0, 0, 0, 0], answer.applied_count));
  const answered = $derived(!!answer.applied_count);
  const median = $derived(answered ? duration(answer.median_seconds) : '—');
  const silent = $derived(answered ? share(answer.no_response_pct) : '—');
</script>

<div class="stats-resp-card">
  <div class="stats-resp-chart">
    {#each bars as one (one.label)}
      <div class="stats-resp-bar-wrap">
        <span class="stats-resp-bar-num">{one.note}</span>
        <div class="stats-resp-bar" class:weekend={one.weekend} style="height: {one.percent}%"></div>
        <span class="stats-resp-bar-label">{one.label}</span>
      </div>
    {/each}
  </div>

  <div class="stats-resp-stats">
    <div>
      <div class="stats-resp-stat-num">{median}</div>
      <div class="stats-resp-stat-label">Медиана от Sent до ответа</div>
    </div>
    <div>
      <div class="stats-resp-stat-num dim">{silent}</div>
      <div class="stats-resp-stat-label">Откликов без ответа</div>
    </div>
  </div>
</div>

<script>
  // Пять показателей в ряд, каждый своей карточкой.
  //
  // Карточками, а не числами внутри одной: их читают по одному — «сколько
  // офферов» и «сколько отказов» разные вопросы, — и общая рамка склеивала бы
  // ответы в список.
  //
  // До ответа моста ряд стоит скелетом из прочерков, уже в цветах: пустое
  // место читалось бы как «показателей нет», а надпись «Загрузка…» на пять
  // карточек — как одна широкая.
  import { KPI, kpiRow } from '$state/stats.js';

  let { answer, period } = $props();

  const rows = $derived(answer ? kpiRow(answer, period) : KPI);
</script>

<div class="stats-kpi-row">
  {#each rows as one (one.key)}
    <div class="stats-card">
      <div class="stats-kpi">
        <span class="big-num stats-kpi-num" data-tone={one.tone}>{answer ? one.total : '—'}</span>
        <span class="stats-kpi-label">{answer ? one.label : '…'}</span>
        {#if answer && one.delta}
          <span class="stats-kpi-delta" data-tone={one.delta.tone}>{one.delta.text}</span>
        {/if}
      </div>
    </div>
  {/each}
</div>

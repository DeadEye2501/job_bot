<script>
  // Счётчики статусов по краям и кольцо между ними.
  //
  // Строка нажимается: иначе число остаётся числом — чтобы посмотреть, что за
  // девять штук, пришлось бы идти в вакансии и набирать тот же отбор руками.
  import DonutChart from './DonutChart.svelte';
  import { donut, statusColumns } from '$state/stats.js';

  let { counts, onpick } = $props();

  const columns = $derived(statusColumns(counts));
  const parts = $derived(donut(counts));
  // Итог считается по всем статусам, а не по нарисованным долям: нулевые в
  // кольцо не попадают, и сумма по нему совпала бы с этой лишь случайно.
  const total = $derived(Object.values(counts).reduce((sum, one) => sum + (one || 0), 0));
</script>

{#snippet column(rows, side)}
  <div class="stats-status-col {side}">
    {#each rows as one (one.name)}
      <div
        class="stats-sc-item"
        role="button"
        tabindex="0"
        title="Открыть вакансии со статусом «{one.name}»"
        onclick={() => onpick(one.name)}
        onkeydown={(event) => event.key === 'Enter' && onpick(one.name)}
      >
        <span class="status-dot" data-status={one.name}></span>
        <span class="stats-sc-name">{one.name}</span>
        <span class="stats-sc-num">{one.count}</span>
      </div>
    {/each}
  </div>
{/snippet}

<div class="stats-status-card">
  {@render column(columns[0], '')}
  <DonutChart {parts} {total} label="Всего" />
  {@render column(columns[1], 'right')}
</div>

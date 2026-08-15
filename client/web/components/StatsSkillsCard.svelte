<script>
  // Навыки вакансий тремя колонками: галочка «моё», имя, полоса частоты, счёт.
  //
  // Число колонок задаётся разметкой, а не оформлением: сетка заполняется
  // сверху вниз, и высота колонки считается от того, сколько навыков приехало.
  import { skillRows, skillRowsPerColumn } from '$state/stats.js';

  let { skills } = $props();

  const rows = $derived(skillRows(skills));
  const perColumn = $derived(skillRowsPerColumn(skills));
</script>

<div class="stats-skills-grid" style="grid-template-rows: repeat({perColumn}, auto);">
  {#each rows as one (one.label)}
    <div class="ruled-row stats-skill-row" class:mine={one.mine} class:first-in-col={one.first}>
      <span class="stats-skill-check">{one.mine ? '✓' : ''}</span>
      <span class="stats-skill-name">{one.label}</span>
      <div class="stats-skill-bar">
        <div class="stats-skill-bar-fill" style="width: {one.percent}%"></div>
      </div>
      <span class="stats-skill-num">{one.count}</span>
    </div>
  {/each}
</div>

<div class="stats-skills-legend">
  <span><span class="leg-dot leg-mine"></span>Есть в моём профиле</span>
  <span><span class="leg-dot leg-other"></span>Не в моём профиле</span>
</div>

<script>
  // Карточка статистики: заголовок и содержимое, пока оно не приехало —
  // «Загрузка…». Ширину в двенадцати колонках сетки называет сам экран: одни
  // карточки идут во всю ширину, другие пополам.
  let { title, ready, span, children } = $props();
</script>

<div class="stats-card stats-col-{span}">
  <div class="stats-card-title">{title}</div>
  {#if ready}
    {@render children()}
  {:else}
    <div class="stats-loading">Загрузка…</div>
  {/if}
</div>

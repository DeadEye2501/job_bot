<script>
  // Карточка статистики: заголовок и содержимое, пока оно не приехало —
  // «Загрузка…». Коробка та же, что у секции настроек: разница только в
  // ширине, и её задаёт сам экран.
  let { title, ready, wide = false, children } = $props();
</script>

<div class="settings-section" class:wide>
  <div class="settings-section-title">{title}</div>
  {#if ready}
    {@render children()}
  {:else}
    <div class="empty-note">Загрузка…</div>
  {/if}
</div>

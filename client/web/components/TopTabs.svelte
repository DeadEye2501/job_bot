<script>
  // Вкладки раздела: одна строка над содержимым экрана.
  let { tabs, active, onpick } = $props();
</script>

<nav class="top-tabs">
  {#each tabs as one (one.key)}
    <button class="tab" class:active={active === one.key} type="button" onclick={() => onpick(one.key)}>
      {one.label}
    </button>
  {/each}
</nav>

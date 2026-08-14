<script>
  // Секция настроек: значок, заголовок, плашка состояния справа и содержимое.
  import StatusPill from './StatusPill.svelte';

  let { icon, title, pill, danger = false, children } = $props();
</script>

<div class="settings-section" class:danger>
  <div class="settings-section-title">
    <span class="material-symbols-outlined">{icon}</span>
    {title}
    {#if pill}
      <StatusPill text={pill.text} tone={pill.tone} title={pill.title} />
    {/if}
  </div>
  {@render children()}
</div>

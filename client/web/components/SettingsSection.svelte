<script>
  // Секция настроек: значок, заголовок, справа плашка состояния и кнопки, ниже
  // содержимое.
  //
  // Кнопки — в шапке, а не под полями: строка шапки и так занята одним
  // заголовком, а отдельная строка под полями ради кнопок удлиняла экран.
  import StatusPill from './StatusPill.svelte';

  let { icon, title, pill, actions = null, danger = false, children } = $props();
</script>

<div class="settings-section" class:danger>
  <div class="settings-section-title">
    <span class="material-symbols-outlined">{icon}</span>
    {title}
    {#if pill || actions}
      <div class="settings-section-side">
        {#if pill}
          <StatusPill text={pill.text} tone={pill.tone} title={pill.title} />
        {/if}
        {#if actions}{@render actions()}{/if}
      </div>
    {/if}
  </div>
  {@render children()}
</div>

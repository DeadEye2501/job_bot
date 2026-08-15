<script>
  // Строка журнала: время, уровень, источник, сообщение. Развёрнутая
  // показывает трассировку и не режет сообщение по ширине.
  let { time, level, tone, source, message, details, expanded, ontoggle } = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="logs-row" class:expanded onclick={() => ontoggle()}>
  <span class="logs-time">{time}</span>
  <span class="logs-level" data-tone={tone}>{level}</span>
  <span class="logs-source">{source}</span>
  <span class="logs-msg">{message}</span>
  {#if expanded && details}
    <div class="logs-details">{details}</div>
  {/if}
</div>

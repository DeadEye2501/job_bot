<script>
  // Строка журнала: время, уровень, источник, сообщение. Развёрнутая
  // показывает трассировку и не режет сообщение по ширине.
  let { time, level, tone, source, message, details, expanded, ontoggle } = $props();
</script>

<!-- Нажимается вся строка, а не значок в ней: строк сотни, и целиться в
     значок ради трассировки человеку не за что. Клавиатуре она отвечает тем
     же — иначе журнал не развернуть, не берясь за мышь. -->
<div
  class="logs-row"
  class:expanded
  role="button"
  tabindex="0"
  onclick={() => ontoggle()}
  onkeydown={(event) => event.key === 'Enter' && ontoggle()}
>
  <span class="logs-time">{time}</span>
  <span class="logs-level" data-tone={tone}>{level}</span>
  <span class="logs-source">{source}</span>
  <span class="logs-msg">{message}</span>
  {#if expanded && details}
    <div class="logs-details">{details}</div>
  {/if}
</div>

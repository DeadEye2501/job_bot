<script>
  // Плашка состояния в заголовке секции: короткое слово и подсказка под ним.
  let { text, tone, title } = $props();
</script>

<span class="status-pill" data-tone={tone} {title}>{text}</span>

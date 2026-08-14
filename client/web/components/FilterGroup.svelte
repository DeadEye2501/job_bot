<script>
  // Группа панели отбора: подпись над своими полями.
  //
  // Подпись стоит над каждой: чипы «Все / Дня / Недели» сами по себе не
  // говорят, чего они срок, а полей в панели девять групп.
  let { label, children } = $props();
</script>

<div class="filter-group">
  <div class="filter-label">{label}</div>
  {@render children()}
</div>

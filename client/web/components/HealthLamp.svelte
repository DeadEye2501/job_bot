<script>
  // Лампочка одной системы: показывает переданное состояние и больше ничего.
  let { name, state, title } = $props();
</script>

<div class="health" data-state={state} {title}>
  <span class="dot"></span>
  <span class="health-label">{name}</span>
</div>

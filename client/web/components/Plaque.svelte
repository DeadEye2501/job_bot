<script>
  // Единственная плашка отказа на всё окно. Показать её решает сборка, здесь
  // только вид.
  let { message, danger } = $props();
</script>

<div class="app-toast" class:visible={Boolean(message)} class:danger role="status">
  {message}
</div>

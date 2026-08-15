<script>
  // Кнопка обхода: треугольник в покое, квадрат на ходу.
  let { running, disabled, title, onpress } = $props();
</script>

<button
  class="icon-btn run-btn"
  class:is-disabled={disabled}
  data-running={running}
  {title}
  aria-disabled={disabled}
  onclick={() => onpress()}
></button>

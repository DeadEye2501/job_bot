<script>
  // Ряд вариантов, выбираемых нажатием: отмечено то, что есть в наборе.
  //
  // Вид приходит доводом, а не вторым компонентом: сегментами — когда
  // вариантов три-четыре и они делят ширину поровну, чипами — когда их
  // одиннадцать и они переносятся на второй этаж. Всё остальное у этих рядов
  // общее, и разошлись бы они молча.
  //
  // Про то, один выбран или несколько, ряд не знает вовсе: это решает набор,
  // который приходит доводом.
  let { options, chosen, look, dots = false, onpick } = $props();
</script>

<div class="choice-row" data-look={look}>
  {#each options as one (one.value)}
    <button
      class="choice"
      class:active={chosen.has(one.value)}
      type="button"
      aria-pressed={chosen.has(one.value)}
      onclick={() => onpick(one.value)}
    >
      {#if dots}<span class="status-dot" data-status={one.value}></span>{/if}
      {one.label}
    </button>
  {/each}
</div>

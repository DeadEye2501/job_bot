<script>
  // Строка шагов мастера: где человек сейчас и сколько ещё осталось.
  //
  // Приглушена на обложках: приветствие и финал шагами не считаются, и
  // подсвеченный на них первый шаг обещал бы, что его уже проходят.
  let { marks, dimmed } = $props();
</script>

<div class="wiz-steps" class:dimmed>
  {#each marks as one, at (one.label)}
    <div class="wiz-step" data-mark={one.mark}>
      <span class="wiz-step-mark">{one.mark === 'done' ? '✓' : at + 1}</span>
      <span class="wiz-step-label">{one.label}</span>
    </div>
  {/each}
</div>

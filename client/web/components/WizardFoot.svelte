<script>
  // Подвал шага мастера: назад, дальше и причина, по которой дальше нельзя.
  //
  // Причина стоит рядом с кнопкой, а не плашкой поверх окна: человек читает её
  // в тот миг, когда нажал, и глядя на то самое поле, которого ей не хватило.
  let { trouble = '', nextLabel, busy = false, onback = null, onnext } = $props();
</script>

<div class="wiz-foot">
  {#if onback}
    <button class="btn" type="button" onclick={onback}>Назад</button>
  {:else}
    <span></span>
  {/if}

  <div class="wiz-foot-right">
    {#if trouble}<span class="wiz-trouble">{trouble}</span>{/if}
    <button class="btn primary" type="button" disabled={busy} onclick={onnext}>
      {nextLabel}
    </button>
  </div>
</div>

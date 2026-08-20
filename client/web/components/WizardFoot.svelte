<script>
  // Подвал шага мастера: назад и дальше.
  //
  // Значок основной кнопки называет действие раньше подписи: «Отправить код» и
  // «Дальше» — разные шаги, и рука узнаёт их по стрелке или самолётику.
  // `children` — место для кнопки, которая стоит перед основной: на шагах
  // поставщика это «Проверить». Своего подвала они из-за неё не заводят.
  let {
    nextLabel,
    nextIcon = '',
    busy = false,
    onback = null,
    onnext,
    children = null,
  } = $props();
</script>

<div class="modal-footer wiz-foot">
  {#if onback}
    <!-- Заперта вместе с основной: уход назад посреди зова оставил бы ответ
         прилетать в экран, которого уже нет. -->
    <button class="btn text" type="button" disabled={busy} onclick={onback}>Назад</button>
  {:else}
    <span></span>
  {/if}

  <div class="wiz-foot-right">
    {#if children}{@render children()}{/if}
    <button class="btn primary" type="button" disabled={busy} onclick={onnext}>
      {nextLabel}
      {#if nextIcon}<span class="material-symbols-outlined">{nextIcon}</span>{/if}
    </button>
  </div>
</div>

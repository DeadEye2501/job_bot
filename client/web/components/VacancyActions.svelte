<script>
  // Меню действий над вакансией: то, что делают с ней редко, но метко.
  //
  // Заперты пункты не запретом нажатия, а объяснением: человеку важнее узнать,
  // почему отправка недоступна, чем не суметь по ней нажать. Причина приходит
  // доводом и показывается плашкой.
  let { blocks, say, onsend, onrerun, onlinkhr, onlinkcompany, onraw, onsource, ondelete } =
    $props();

  let open = $state(false);

  function pick(action, blocked) {
    open = false;
    if (blocked) return say(blocked);
    return action();
  }
</script>

<div class="pop-wrap">
  <button class="icon-btn" type="button" title="Действия" onclick={() => (open = !open)}>
    <span class="material-symbols-outlined">more_vert</span>
  </button>

  {#if open}
    <!-- Закрывается по уходу мыши, как и прочие всплывающие списки окна:
         нажатие мимо здесь не годится, оно уходит в карточку под меню. -->
    <div class="pop menu" role="menu" tabindex="-1" onmouseleave={() => (open = false)}>
      <button
        class="menu-item"
        class:blocked={blocks.send}
        type="button"
        onclick={() => pick(onsend, blocks.send)}
      >
        <span class="material-symbols-outlined">send</span>
        Отправить отклик
      </button>
      <button
        class="menu-item"
        class:blocked={blocks.rerun}
        type="button"
        onclick={() => pick(onrerun, blocks.rerun)}
      >
        <span class="material-symbols-outlined">refresh</span>
        Разобрать заново
      </button>

      <div class="menu-line"></div>

      <button class="menu-item" type="button" onclick={() => pick(onlinkhr, '')}>
        <span class="material-symbols-outlined">link</span>
        Связать с другим HR
      </button>
      <button class="menu-item" type="button" onclick={() => pick(onlinkcompany, '')}>
        <span class="material-symbols-outlined">link</span>
        Связать с другой компанией
      </button>

      <div class="menu-line"></div>

      <button class="menu-item" type="button" onclick={() => pick(onraw, '')}>
        <span class="material-symbols-outlined">code</span>
        Исходный текст объявления
      </button>
      <button class="menu-item" type="button" onclick={() => pick(onsource, '')}>
        <span class="material-symbols-outlined">open_in_new</span>
        Открыть в Telegram
      </button>

      <div class="menu-line"></div>

      <button class="menu-item danger" type="button" onclick={() => pick(ondelete, '')}>
        <span class="material-symbols-outlined">delete</span>
        Удалить
      </button>
    </div>
  {/if}
</div>

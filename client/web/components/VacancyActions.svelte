<script>
  // Меню действий над вакансией: то, что делают с ней редко, но метко.
  //
  // Заперты пункты не запретом нажатия, а объяснением: человеку важнее узнать,
  // почему отправка недоступна, чем не суметь по ней нажать. Причина приходит
  // доводом, стоит подсказкой при наведении — до нажатия — и повторяется
  // плашкой, если по пункту всё-таки нажали.
  let { blocks, say, onsend, onrerun, onlinkhr, onlinkcompany, onraw, onsource, ondelete } =
    $props();

  let open = $state(false);
  let root = $state(null);

  function pick(action, blocked) {
    open = false;
    if (blocked) return say(blocked);
    return action();
  }

  $effect(() => {
    if (!open) return;
    // Нажатие мимо закрывает меню. Своим узлом, а не по имени класса: всплывающих
    // окошек на карточке два, и «мимо» у каждого своё.
    const away = (event) => {
      if (root !== null && !root.contains(event.target)) open = false;
    };
    document.addEventListener('click', away);
    return () => document.removeEventListener('click', away);
  });
</script>

<div class="pop-wrap" bind:this={root}>
  <button class="icon-btn" type="button" title="Действия" onclick={() => (open = !open)}>
    <span class="material-symbols-outlined">more_vert</span>
  </button>

  {#if open}
    <div class="pop menu" role="menu" tabindex="-1">
      <button
        class="menu-item"
        class:blocked={blocks.send}
        type="button"
        title={blocks.send || null}
        onclick={() => pick(onsend, blocks.send)}
      >
        <span class="material-symbols-outlined">send</span>
        Отправить отклик
      </button>
      <button
        class="menu-item"
        class:blocked={blocks.rerun}
        type="button"
        title={blocks.rerun || null}
        onclick={() => pick(onrerun, blocks.rerun)}
      >
        <span class="material-symbols-outlined">refresh</span>
        Прогнать пайплайн заново
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
        Открыть raw_text
      </button>
      <button
        class="menu-item"
        class:blocked={blocks.source}
        type="button"
        title={blocks.source || null}
        onclick={() => pick(onsource, blocks.source)}
      >
        <span class="material-symbols-outlined">open_in_new</span>
        Перейти к каналу-источнику
      </button>

      <div class="menu-line"></div>

      <button class="menu-item danger" type="button" onclick={() => pick(ondelete, '')}>
        <span class="material-symbols-outlined">delete</span>
        Удалить
      </button>
    </div>
  {/if}
</div>

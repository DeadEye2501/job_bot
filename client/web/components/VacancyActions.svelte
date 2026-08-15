<script>
  // Пункты меню действий над вакансией: то, что делают с ней редко, но метко.
  //
  // Заперты пункты не запретом нажатия, а объяснением: человеку важнее узнать,
  // почему отправка недоступна, чем не суметь по ней нажать. Причина приходит
  // доводом, стоит подсказкой при наведении — до нажатия — и повторяется
  // плашкой, если по пункту всё-таки нажали.
  import ActionsMenu from './ActionsMenu.svelte';

  let { blocks, say, onsend, onrerun, onlinkhr, onlinkcompany, onraw, onsource, ondelete } =
    $props();

  function pick(close, action, blocked) {
    close();
    if (blocked) return say(blocked);
    return action();
  }
</script>

<ActionsMenu>
  {#snippet children(close)}
    <button
      class="menu-item"
      class:blocked={blocks.send}
      type="button"
      title={blocks.send || null}
      onclick={() => pick(close, onsend, blocks.send)}
    >
      <span class="material-symbols-outlined">send</span>
      Отправить отклик
    </button>
    <button
      class="menu-item"
      class:blocked={blocks.rerun}
      type="button"
      title={blocks.rerun || null}
      onclick={() => pick(close, onrerun, blocks.rerun)}
    >
      <span class="material-symbols-outlined">refresh</span>
      Прогнать пайплайн заново
    </button>

    <div class="menu-line"></div>

    <button class="menu-item" type="button" onclick={() => pick(close, onlinkhr, '')}>
      <span class="material-symbols-outlined">link</span>
      Связать с другим HR
    </button>
    <button class="menu-item" type="button" onclick={() => pick(close, onlinkcompany, '')}>
      <span class="material-symbols-outlined">link</span>
      Связать с другой компанией
    </button>

    <div class="menu-line"></div>

    <button class="menu-item" type="button" onclick={() => pick(close, onraw, '')}>
      <span class="material-symbols-outlined">code</span>
      Открыть raw_text
    </button>
    <button
      class="menu-item"
      class:blocked={blocks.source}
      type="button"
      title={blocks.source || null}
      onclick={() => pick(close, onsource, blocks.source)}
    >
      <span class="material-symbols-outlined">open_in_new</span>
      Перейти к каналу-источнику
    </button>

    <div class="menu-line"></div>

    <button class="menu-item danger" type="button" onclick={() => pick(close, ondelete, '')}>
      <span class="material-symbols-outlined">delete</span>
      Удалить
    </button>
  {/snippet}
</ActionsMenu>

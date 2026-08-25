<script>
  // Пункты меню действий над вакансией: то, что делают с ней редко, но метко.
  //
  // Заперты пункты не запретом нажатия, а объяснением: человеку важнее узнать,
  // почему отправка недоступна, чем не суметь по ней нажать. Причина приходит
  // доводом, стоит подсказкой при наведении — до нажатия — и повторяется
  // плашкой, если по пункту всё-таки нажали.
  import ActionsMenu from './ActionsMenu.svelte';
  import MenuItem from './MenuItem.svelte';

  let { blocks, say, onsend, onrerun, onlinkhr, onlinkcompany, onraw, onsource, ondelete } =
    $props();

  function pick(action, blocked) {
    if (blocked) return say(blocked);
    return action();
  }
</script>

<ActionsMenu>
  {#snippet children(close)}
    <MenuItem
      icon="send"
      label="Отправить отклик"
      title={blocks.send || null}
      blocked={Boolean(blocks.send)}
      {close}
      onpick={() => pick(onsend, blocks.send)}
    />
    <MenuItem
      icon="refresh"
      label="Прогнать пайплайн заново"
      title={blocks.rerun || null}
      blocked={Boolean(blocks.rerun)}
      {close}
      onpick={() => pick(onrerun, blocks.rerun)}
    />

    <div class="menu-line"></div>

    <MenuItem icon="link" label="Связать с другим HR" {close} onpick={onlinkhr} />
    <MenuItem icon="link" label="Связать с другой компанией" {close} onpick={onlinkcompany} />

    <div class="menu-line"></div>

    <MenuItem
      icon="code"
      label="Открыть raw_text"
      title={blocks.raw || null}
      blocked={Boolean(blocks.raw)}
      {close}
      onpick={() => pick(onraw, blocks.raw)}
    />
    <MenuItem
      icon="open_in_new"
      label="Перейти к каналу-источнику"
      title={blocks.source || null}
      blocked={Boolean(blocks.source)}
      {close}
      onpick={() => pick(onsource, blocks.source)}
    />

    <div class="menu-line"></div>

    <MenuItem icon="delete" label="Удалить" danger {close} onpick={ondelete} />
  {/snippet}
</ActionsMenu>

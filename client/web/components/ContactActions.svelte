<script>
  // Меню действий над карточкой контакта: слить, отправить в отсев, удалить.
  //
  // Одно на человека и компанию: различаются они одним словом в первом пункте
  // — «слить с другим HR» против «слить с другой компанией», — а написаны эти
  // меню были дважды по тридцать четыре строки.
  import ActionsMenu from './ActionsMenu.svelte';
  import BlacklistMenuItem from './BlacklistMenuItem.svelte';
  import MenuItem from './MenuItem.svelte';

  let { mergeLabel, blocked, onmerge, onblock, onunblock, ondelete } = $props();
</script>

<ActionsMenu>
  {#snippet children(close)}
    <MenuItem icon="merge" label={mergeLabel} {close} onpick={onmerge} />
    <BlacklistMenuItem {blocked} {close} {onblock} {onunblock} />

    <div class="menu-line"></div>

    <MenuItem icon="delete" label="Удалить" danger {close} onpick={ondelete} />
  {/snippet}
</ActionsMenu>

<script>
  // Меню действий карточки: свои пункты сверху, ниже — отправить в отсев и,
  // за чертой, удалить.
  //
  // Хвост меню у человека, компании, канала и агрегатора один и тот же; свои у
  // них только верхние пункты (`lead`) и подпись удаления. `removable` гасит
  // хвост целиком — у «Поиска по сети» нет ни отсева, ни удаления. `deleteTip`
  // запирает удаление и называет почему.
  import ActionsMenu from './ActionsMenu.svelte';
  import BlacklistMenuItem from './BlacklistMenuItem.svelte';
  import MenuItem from './MenuItem.svelte';

  let {
    lead,
    blocked,
    deleteLabel = 'Удалить',
    deleteTip = '',
    removable = true,
    onblock,
    onunblock,
    ondelete,
  } = $props();
</script>

<ActionsMenu>
  {#snippet children(close)}
    {@render lead(close)}
    {#if removable}
      <BlacklistMenuItem {blocked} {close} {onblock} {onunblock} />

      <div class="menu-line"></div>

      <MenuItem
        icon="delete"
        label={deleteLabel}
        danger
        title={deleteTip || null}
        disabled={!!deleteTip}
        {close}
        onpick={ondelete}
      />
    {/if}
  {/snippet}
</ActionsMenu>

<script>
  // Клавиатура открытого окна: Escape закрывает, Enter подтверждает.
  //
  // Отдельным элементом, а не строкой в каждом окне: окон пять, и слушают они
  // всю страницу — где стоит фокус, там и нажали. Место в стопке окно занимает
  // здесь же: нажатие достаётся верхнему, иначе один Escape закрыл бы карточку
  // вместе с подборщиком и подтверждением над ним.
  import { modalPress, opened } from '$state/keys.js';

  let { close, confirm = null } = $props();

  const mine = {};

  $effect(() => opened(mine));
</script>

<svelte:window onkeydown={(event) => modalPress(event, mine, { close, confirm })} />

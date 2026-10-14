<script>
  // Выпадающий список со своим видом.
  //
  // Не системный `<select>`: тот рисуется средствами системы и в тёмном окне
  // выглядит светлой заплатой, а его список нельзя ни оформить, ни сузить.
  import { whileOpen } from '$state/outside.js';

  import DropButton from './DropButton.svelte';
  import DropPanel from './DropPanel.svelte';

  let { options, value, placeholder = '', onpick } = $props();

  let open = $state(false);
  let root = $state(null);

  $effect(() => {
    // Закрывается нажатием мимо: список накрывает строки под собой, и уйти от
    // него человек может куда угодно — хоть в соседнюю строку, хоть в поле над
    // ней. «Мимо» считается по своему узлу: списков на вкладке столько же,
    // сколько строк языка, и по классу они друг от друга не отличаются.
    return whileOpen(open, () => root, () => (open = false));
  });
</script>

<div class="cdd" class:open bind:this={root}>
  <DropButton label={value || placeholder} empty={!value} {open} ontoggle={() => (open = !open)} />
  {#if open}
    <DropPanel
      {options}
      {value}
      onpick={(one) => {
        open = false;
        onpick(one);
      }}
    />
  {/if}
</div>

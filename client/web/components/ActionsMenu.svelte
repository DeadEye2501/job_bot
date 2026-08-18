<script>
  // Меню действий под кнопкой-значком: раскрывает список и закрывает его.
  //
  // О самих пунктах не знает ничего — их рисует тот, кто позвал, и получает
  // сюда же закрывающий зов: нажатый пункт обязан убрать за собой окошко.
  import { closeOnClickAway } from '$state/outside.js';

  let { children } = $props();

  let open = $state(false);
  let root = $state(null);

  $effect(() => {
    if (!open) return;
    // Нажатие мимо закрывает меню. Своим узлом, а не по имени класса:
    // всплывающих окошек на карточке несколько, и «мимо» у каждого своё.
    return closeOnClickAway(() => root, () => (open = false));
  });
</script>

<div class="pop-wrap" bind:this={root}>
  <button class="icon-btn" type="button" title="Действия" onclick={() => (open = !open)}>
    <span class="material-symbols-outlined">more_vert</span>
  </button>

  {#if open}
    <div class="pop menu" role="menu" tabindex="-1">
      {@render children(() => (open = false))}
    </div>
  {/if}
</div>

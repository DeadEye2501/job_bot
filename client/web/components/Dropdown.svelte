<script>
  // Выпадающий список со своим видом.
  //
  // Не системный `<select>`: тот рисуется средствами системы и в тёмном окне
  // выглядит светлой заплатой, а его список нельзя ни оформить, ни сузить.
  let { options, value, onpick } = $props();

  let open = $state(false);
</script>

<div class="cdd" class:open>
  <button class="cdd-btn" type="button" onclick={() => (open = !open)}>
    <span class="cdd-label">{value}</span>
    <span class="material-symbols-outlined">expand_more</span>
  </button>
  {#if open}
    <!-- Закрывается по выбору и по уходу мыши: без второго открытый список
         перекрывал бы соседние строки, пока по нему не нажмут. -->
    <div class="cdd-panel" role="listbox" tabindex="-1" onmouseleave={() => (open = false)}>
      {#each options as one (one)}
        <button
          class="cdd-option"
          class:active={one === value}
          type="button"
          onclick={() => {
            open = false;
            onpick(one);
          }}
        >
          {one}
        </button>
      {/each}
    </div>
  {/if}
</div>

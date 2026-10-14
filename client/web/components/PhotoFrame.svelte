<script>
  // Рамка фото в анкете: снимок заполняет её целиком, нажатие на рамку —
  // выбор файла, крестик в углу — очистка. Что показывать и что делать,
  // приходит параметрами.
  //
  // Выбору рамка отдаёт свою пропорцию: снимок обрезают ровно под неё.
  let { url, onpick, onclear } = $props();

  let frame = $state(null);
</script>

<div class="photo-frame" bind:this={frame}>
  <button
    class="photo-pick"
    type="button"
    title="Выбрать фото"
    onclick={() => onpick(frame.offsetWidth / frame.offsetHeight)}
  >
    {#if url}
      <img src={url} alt="Фото" />
    {:else}
      <span class="material-symbols-outlined">add_a_photo</span>
    {/if}
  </button>
  {#if url}
    <button class="photo-clear" type="button" title="Убрать фото" onclick={onclear}>
      <span class="material-symbols-outlined">close</span>
    </button>
  {/if}
</div>

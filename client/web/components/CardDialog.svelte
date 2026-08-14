<script>
  // Оправа карточки: окно поверх списка и три его состояния.
  //
  // Карточек три — канал, компания, человек, — и все они открываются поверх
  // списка, ждут ответа моста и умеют отказать. Своё у каждой только то, что
  // внутри.
  //
  // Отказ не запирает окно: человеку нужно хотя бы выйти из него, а плашку
  // беды он уже увидел.
  let { trouble, ready, onclose, children } = $props();
</script>

<div class="modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && onclose()}>
  <div class="modal-dialog card-dialog" role="dialog" aria-modal="true">
    {#if trouble}
      <div class="empty-note">{trouble}</div>
      <div class="modal-actions">
        <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
      </div>
    {:else if !ready}
      <div class="empty-note">Загрузка…</div>
    {:else}
      {@render children()}
    {/if}
  </div>
</div>

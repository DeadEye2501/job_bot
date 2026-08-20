<script>
  // Шапка окна: значок, заголовок и крестик.
  //
  // `meta` — приписка бледнее заголовка: ею окно исходного текста называет
  // номер вакансии, по которому его и открыли.
  let { icon, title, meta = '', onclose } = $props();
</script>

<div class="modal-head">
  <span class="material-symbols-outlined">{icon}</span>
  <div class="modal-title">
    {title}
    {#if meta}<span class="modal-title-meta">{meta}</span>{/if}
  </div>
  <button class="modal-close" type="button" title="Закрыть" onclick={() => onclose()}>
    <span class="material-symbols-outlined">close</span>
  </button>
</div>

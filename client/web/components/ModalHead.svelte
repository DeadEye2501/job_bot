<script>
  // Шапка окна: значок, заголовок и крестик.
  //
  // `meta` — приписка бледнее заголовка: ею окно исходного текста называет
  // номер вакансии, по которому его и открыли.
  //
  // `onclose` необязателен: у окна заведения второго выхода нет — закрывают
  // его «Отменой», — и крестик там был бы кнопкой, которой не просили.
  let { icon, title, meta = '', onclose = null } = $props();
</script>

<div class="bar modal-head">
  <span class="material-symbols-outlined">{icon}</span>
  <div class="modal-title">
    {title}
    {#if meta}<span class="modal-title-meta">{meta}</span>{/if}
  </div>
  {#if onclose}
    <button class="modal-close" type="button" title="Закрыть" onclick={() => onclose()}>
      <span class="material-symbols-outlined">close</span>
    </button>
  {/if}
</div>

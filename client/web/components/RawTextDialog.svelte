<script>
  // Исходный текст объявления: то, что бот разбирал, — как оно пришло.
  //
  // Открывают его, когда разбор вышел кривым: по тексту видно, чего в
  // объявлении не было вовсе, а что модель прочла не так.
  let { note, text, oncopy, onclose } = $props();
</script>

<div class="modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && onclose()}>
  <div class="modal-dialog card-dialog" role="dialog" aria-modal="true">
    <div class="modal-title">
      <span class="material-symbols-outlined">code</span>
      Исходный текст
      <span class="raw-note">{note}</span>
    </div>

    <pre class="raw-text">{text}</pre>

    <div class="modal-actions">
      <button class="btn" type="button" onclick={oncopy}>
        <span class="material-symbols-outlined">content_copy</span>
        Скопировать
      </button>
      <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
    </div>
  </div>
</div>

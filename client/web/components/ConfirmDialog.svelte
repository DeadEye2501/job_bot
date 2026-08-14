<script>
  // Спросить человека, прежде чем делать необратимое.
  let { message, confirmLabel, onconfirm, oncancel } = $props();
</script>

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(event) => event.target === event.currentTarget && oncancel()}
>
  <div class="modal-dialog" role="dialog" aria-modal="true">
    <div class="modal-message">{message}</div>
    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button class="btn danger" type="button" onclick={() => onconfirm()}>{confirmLabel}</button>
    </div>
  </div>
</div>

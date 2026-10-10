<script>
  // Спросить человека, прежде чем делать необратимое.
  //
  // Кнопка подтверждения красная: это последнее, что может остановить руку.
  import ModalShell from './ModalShell.svelte';

  let { message, confirmLabel, onconfirm, oncancel } = $props();
</script>

<ModalShell onclose={oncancel} confirm={onconfirm}>
  {#snippet children()}
    <div class="modal-message">{message}</div>
    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button class="btn danger" type="button" onclick={() => onconfirm()}>{confirmLabel}</button>
    </div>
  {/snippet}
</ModalShell>

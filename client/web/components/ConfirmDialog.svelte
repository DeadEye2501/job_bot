<script>
  // Спросить человека, прежде чем делать необратимое.
  //
  // `tone` — вид кнопки подтверждения. По умолчанию красная: окно заводилось
  // под удаление, и там красный — последнее, что может остановить руку. Но
  // спрашивают им и про отправку отклика, а красная «Отправить» читается как
  // «Удалить».
  import ModalShell from './ModalShell.svelte';

  let { message, confirmLabel, tone = 'danger', onconfirm, oncancel } = $props();
</script>

<ModalShell onclose={oncancel} confirm={onconfirm}>
  {#snippet children()}
    <div class="modal-message">{message}</div>
    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button class="btn {tone}" type="button" onclick={() => onconfirm()}>{confirmLabel}</button>
    </div>
  {/snippet}
</ModalShell>

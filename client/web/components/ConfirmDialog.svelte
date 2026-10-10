<script>
  // Спросить человека, прежде чем делать необратимое.
  //
  // Кнопка подтверждения красная: это последнее, что может остановить руку.
  //
  // `locked` — чем подтверждение заперто сейчас; пусто — не заперто. Запирают
  // окно, пока оно открыто: обход, начатый, пока человек читал вопрос, мост уже
  // не пустит, и кнопка говорит об этом сама, а Enter её не обходит.
  import ModalShell from './ModalShell.svelte';

  let { message, confirmLabel, locked = '', onconfirm, oncancel } = $props();
</script>

<ModalShell onclose={oncancel} confirm={locked ? null : onconfirm}>
  {#snippet children()}
    <div class="modal-message">{message}</div>
    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button
        class="btn danger"
        type="button"
        disabled={!!locked}
        title={locked || null}
        onclick={() => onconfirm()}
      >
        {confirmLabel}
      </button>
    </div>
  {/snippet}
</ModalShell>

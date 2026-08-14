<script>
  // Смена статуса: чем он станет и почему.
  //
  // Причина необязательна: половина переходов очевидна из переписки, и
  // требовать слов к каждому значило бы получать их пустыми.
  import { STATUS_CHOICES } from '$state/statuses.js';

  import ChoiceRow from './ChoiceRow.svelte';

  let { status, saving, onapply, oncancel } = $props();

  let chosen = $state(status);
  let note = $state('');
</script>

<div class="status-picker">
  <ChoiceRow
    options={STATUS_CHOICES}
    chosen={new Set([chosen])}
    look="chip"
    dots
    onpick={(value) => (chosen = value)}
  />

  <textarea class="input" placeholder="Причина (необязательно)" bind:value={note}></textarea>

  <div class="modal-actions">
    <button class="btn" type="button" onclick={oncancel}>Отмена</button>
    <button class="btn primary" type="button" disabled={saving} onclick={() => onapply(chosen, note)}>
      {saving ? 'Сохраняю…' : 'Применить'}
    </button>
  </div>
</div>

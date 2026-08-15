<script>
  // Окно заведения канала: одно поле, пояснение под ним и две кнопки.
  //
  // Своим окном, а не общим спрашивающим: у этого есть шапка с крестиком, свой
  // подвал и строка отказа внутри — канал заводят по нику, и ошибку в нике
  // объясняют там же, где его набирали, а не общей плашкой поверх окна.
  import ModalKeys from './ModalKeys.svelte';

  let { value, trouble, saving, oninput, onadd, onclose } = $props();
</script>

<ModalKeys close={onclose} />

<div class="modal-backdrop" role="presentation">
  <div class="modal-dialog add-channel" role="dialog" aria-modal="true">
    <div class="modal-head">
      <span class="material-symbols-outlined">add_circle</span>
      <div class="modal-title">Добавить канал</div>
      <button class="modal-close" type="button" title="Закрыть" onclick={() => onclose()}>
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>

    <div class="modal-body">
      <!-- svelte-ignore a11y_autofocus -->
      <input
        class="cnt-input"
        autofocus
        maxlength="200"
        placeholder="@username канала или t.me/..."
        {value}
        oninput={(event) => oninput(event.currentTarget.value)}
        onkeydown={(event) => event.key === 'Enter' && onadd()}
      />
      <div class="cnt-add-hint">Название и аватар подгрузятся из Telegram автоматически.</div>
      {#if trouble}
        <div class="modal-error">{trouble}</div>
      {/if}
    </div>

    <div class="modal-footer">
      <button class="btn" type="button" onclick={() => onclose()}>Отмена</button>
      <button class="btn primary" type="button" disabled={saving || !value.trim()} onclick={() => onadd()}>
        {saving ? 'Добавляю…' : 'Добавить'}
      </button>
    </div>
  </div>
</div>

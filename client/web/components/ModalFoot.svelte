<script>
  // Подвал окна: «Отмена» и основная кнопка.
  //
  // Основная заперта, пока не набрано то, без чего делать нечего, и на время
  // ответа моста: второе нажатие ушло бы в уже начатую работу, а подпись
  // говорит, что она идёт. `tip` — почему основная заперта, когда это не
  // видно из самого окна.
  let { label, busyLabel, busy = false, ready = true, tip = '', oncancel, onconfirm } = $props();
</script>

<div class="modal-footer">
  <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
  <button
    class="btn primary"
    type="button"
    disabled={busy || !ready}
    title={tip || null}
    onclick={() => onconfirm()}
  >
    {busy ? busyLabel : label}
  </button>
</div>

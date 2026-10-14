<script>
  // Подвал окна: отказ и основная кнопка.
  //
  // Основная заперта, пока не набрано то, без чего делать нечего, и на время
  // ответа моста: второе нажатие ушло бы в уже начатую работу, а подпись
  // говорит, что она идёт. `tip` — почему основная заперта, когда это не
  // видно из самого окна. `busyLabel` нужен только окну, которое ждёт моста.
  //
  // `cancelLabel` — подпись отказа, если он не «Отмена»; `leading` — кнопки
  // перед ним: у подтверждения отправки выходов три, и третий — «Свернуть».
  let {
    label,
    busyLabel = label,
    busy = false,
    ready = true,
    tip = '',
    cancelLabel = 'Отмена',
    leading = null,
    oncancel,
    onconfirm,
  } = $props();
</script>

<div class="modal-footer">
  {#if leading}{@render leading()}{/if}
  <button class="btn" type="button" onclick={() => oncancel()}>{cancelLabel}</button>
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

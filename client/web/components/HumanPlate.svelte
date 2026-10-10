<script>
  // Плашка ожидания человека: что требуется и галочка «справился».
  //
  // Нажатие на текст выводит вперёд браузер, где ждут человека; галочка
  // отпускает агента. Не прошла капча — агент позовёт снова, и плашка вернётся.
  let { text, onreveal, ondone } = $props();
</script>

<div class="human-plate">
  <button class="human-plate-text" type="button" onclick={() => onreveal()}>{text}</button>
  <button class="human-plate-done" type="button" onclick={() => ondone()}>
    <span class="material-symbols-outlined">check</span>
  </button>
</div>

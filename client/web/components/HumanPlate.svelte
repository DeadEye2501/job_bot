<script>
  // Плашка ожидания человека: что требуется и галочка «справился».
  //
  // Нажатие на текст выводит вперёд то, где ждут человека, — браузер или окно
  // подтверждения; галочка отпускает откликателя. Не прошла капча — агент
  // позовёт снова, и плашка вернётся. `confirm` — вид плашки подтверждения;
  // `blocked` — почему галочку сейчас нажать нельзя, пусто — можно.
  let { text, confirm = false, blocked = '', onreveal, ondone } = $props();
</script>

<div class="human-plate" class:confirm>
  <button class="human-plate-text" type="button" onclick={() => onreveal()}>{text}</button>
  <button
    class="human-plate-done"
    type="button"
    disabled={Boolean(blocked)}
    title={blocked || null}
    onclick={() => ondone()}
  >
    <span class="material-symbols-outlined">check</span>
  </button>
</div>

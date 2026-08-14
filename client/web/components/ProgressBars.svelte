<script>
  // Ход обхода: две полосы и подпись. Считает доли и слова чужой слой, сюда
  // они приходят готовыми.
  let { channels, messages, text } = $props();

  /** Ширина заливки — или пусто, когда итог неизвестен.
   *
   * Пусто, а не «0%»: бегущую полосу рисует правило таблицы, а встроенный
   * стиль сильнее любого селектора и перебил бы его. Напиши здесь ноль — и
   * анимация честно крутила бы полосу нулевой ширины.
   */
  const filled = (one) => (one.unknown ? '' : `width: ${one.percent}%`);
</script>

<div class="progress-wrap">
  <div class="progress-bars">
    <div class="progress-bar" data-indeterminate={messages.unknown}>
      <div class="progress-fill" style={filled(messages)}></div>
    </div>
    <div class="progress-bar" data-indeterminate={channels.unknown}>
      <div class="progress-fill" style={filled(channels)}></div>
    </div>
  </div>
  <div class="progress-caption">{text}</div>
</div>

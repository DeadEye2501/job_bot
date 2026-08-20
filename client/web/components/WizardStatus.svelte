<script>
  // Строка состояния шага мастера: чем шаг занят и чем кончилось.
  //
  // Своим компонентом: таких строк три — резюме, Telegram и поставщик, — и
  // написаны они были порознь. Карты значков успели разойтись: у двоих тона
  // было два, у третьего три, и удача на первых двух рисовалась пустым местом.
  //
  // Пустое состояние компонент разбирает сам: у всех троих строка появляется
  // ровно тогда, когда шагу есть что сказать.
  const ICONS = { busy: 'progress_activity', ok: 'check_circle', err: 'error' };

  let { status } = $props();
</script>

{#if status}
  <div class="status-row" data-tone={status.tone}>
    <span class="material-symbols-outlined">{ICONS[status.tone]}</span>
    <span>{status.text}</span>
  </div>
{/if}

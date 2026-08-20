<script>
  // Пункт меню действий: значок, подпись и закрытие меню за собой.
  //
  // Меню закрывает сам: оставшееся открытым окошко перекрывает ту самую строку,
  // которую пункт и поменял. Написано это было голым `close()` в девяти местах
  // — и в девяти же местах его можно было забыть.
  //
  // Про причины пункт не знает: `title` — подсказка при наведении, `blocked` —
  // помечен ли он недоступным, `disabled` — не нажимается ли вовсе. Что из
  // этого чем заполнить, решает меню: у вакансии заслон объясняют плашкой по
  // нажатию, у канала пункт просто заперт.
  let {
    icon,
    label,
    danger = false,
    title = null,
    blocked = false,
    disabled = false,
    close,
    onpick,
  } = $props();
</script>

<button
  class="menu-item"
  class:danger
  class:blocked
  type="button"
  {title}
  {disabled}
  onclick={() => {
    close();
    onpick();
  }}
>
  <span class="material-symbols-outlined">{icon}</span>
  {label}
</button>

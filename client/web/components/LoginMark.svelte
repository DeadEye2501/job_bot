<script>
  // Вход на сайт значком рядом с именем агрегатора: он же показывает, выполнен
  // ли вход, и по нажатию открывает сайт войти (заново). `mark` — выполнен ли
  // вход, значок и подпись (`state/aggregators.loginMark`).
  let { mark, disabled, onlogin } = $props();
</script>

<button
  class="icon-btn login-mark"
  class:done={mark.done}
  type="button"
  title={mark.title}
  {disabled}
  onclick={() => onlogin()}
>
  <span class="material-symbols-outlined">{mark.icon}</span>
</button>

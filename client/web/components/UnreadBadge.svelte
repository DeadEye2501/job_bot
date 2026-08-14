<script>
  // Счётчик непрочитанного. Только счёт: список переписок открывается с экрана
  // контактов, а он ещё не переехал, и кнопка, которой некуда вести, была бы
  // обманом.
  let { count } = $props();
</script>

<div class="badge-unread" data-has-unread={count > 0} title="Непрочитанные переписки">
  <span class="material-symbols-outlined">mail</span>
  <span class="count">{count}</span>
</div>

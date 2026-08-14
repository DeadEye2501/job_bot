<script>
  // Поля нового человека: то, чем его потом находят.
  //
  // Заводят человека из двух мест — из списка контактов и из подборщика связи
  // вакансии, — а поля у него одни: мост читает ровно эти. Разойдись их
  // подписи, одно и то же поле называлось бы в окне по-разному.
  //
  // Черновик правится на месте: он приходит своим объектом от того, кто его
  // потом и отправит.
  let { draft, onenter } = $props();
</script>

<!-- svelte-ignore a11y_autofocus -->
<input
  class="input"
  autofocus
  placeholder="Имя"
  bind:value={draft.name}
  onkeydown={(event) => event.key === 'Enter' && onenter()}
/>
<input class="input" placeholder="Ник в Telegram" bind:value={draft.telegram_username} />
<input
  class="input"
  placeholder="Номер учётной записи Telegram"
  bind:value={draft.telegram_user_id}
/>
<textarea class="textarea" placeholder="Заметки" bind:value={draft.notes}></textarea>

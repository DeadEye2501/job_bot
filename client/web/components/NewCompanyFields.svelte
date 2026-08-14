<script>
  // Поля новой компании: то, чем её потом находят и узнают в объявлениях.
  //
  // Заводят компанию из двух мест — из списка контактов и из подборщика связи
  // вакансии, — а поля у неё одни: мост читает ровно эти. Разойдись их
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
  placeholder="Название"
  bind:value={draft.name}
  onkeydown={(event) => event.key === 'Enter' && onenter()}
/>
<input class="input" placeholder="Сайт или домен" bind:value={draft.website} />
<input class="input" placeholder="Другие написания через запятую" bind:value={draft.aliases} />
<textarea class="textarea" placeholder="Заметки" bind:value={draft.notes}></textarea>

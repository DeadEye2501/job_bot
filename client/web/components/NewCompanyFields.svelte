<script>
  // Поля новой компании: то, чем её потом находят и узнают в объявлениях.
  //
  // Заводят компанию из двух мест — из списка контактов и из подборщика связи
  // вакансии, — а поля у неё одни: мост читает ровно эти. Разойдись их
  // подписи, одно и то же поле называлось бы в окне по-разному.
  //
  // Потолки длины те же, что держит база: обрезанное на записи значение
  // человек прочёл бы как потерянное.
  //
  // Черновик правится на месте: он приходит своим объектом от того, кто его
  // потом и отправит.
  let { draft } = $props();
</script>

<input
  class="input"
  maxlength="120"
  placeholder="Название (обязательно)"
  bind:value={draft.name}
/>
<input
  class="input"
  maxlength="200"
  placeholder="Сайт / домен (опционально)"
  bind:value={draft.website}
/>
<input
  class="input"
  maxlength="300"
  placeholder="Алиасы через запятую (опционально)"
  bind:value={draft.aliases}
/>
<textarea
  class="textarea"
  maxlength="2000"
  placeholder="Заметки"
  bind:value={draft.notes}
></textarea>

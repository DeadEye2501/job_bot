<script>
  // Поля нового человека: то, чем его потом находят.
  //
  // Заводят человека из двух мест — из списка контактов и из подборщика связи
  // вакансии, — а поля у него одни: мост читает ровно эти. Разойдись их
  // подписи, одно и то же поле называлось бы в окне по-разному.
  //
  // Потолки длины те же, что держит база: обрезанное на записи значение
  // человек прочёл бы как потерянное.
  //
  // Черновик правится на месте: он приходит своим объектом от того, кто его
  // потом и отправит.
  let { draft } = $props();
</script>

<input class="input" maxlength="120" placeholder="Имя" bind:value={draft.name} />
<input
  class="input"
  maxlength="64"
  placeholder="Telegram @username (без @)"
  bind:value={draft.telegram_username}
/>
<!-- Номер учётной записи — только цифры: на телефоне открывается цифровая
     раскладка, а мост всё равно приводит его к числу. -->
<input
  class="input"
  inputmode="numeric"
  maxlength="20"
  placeholder="telegram_user_id (опционально)"
  bind:value={draft.telegram_user_id}
/>
<textarea
  class="textarea"
  maxlength="2000"
  placeholder="Заметки"
  bind:value={draft.notes}
></textarea>

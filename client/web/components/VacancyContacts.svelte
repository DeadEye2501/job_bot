<script>
  // Контакты вакансии, кроме Telegram-HR: подпись с «+ Контакт» и список, где
  // каждый контакт открывается нажатием и убирается крестиком.
  //
  // Куда ведёт нажатие, решает тот, кто позвал: здесь только значение строки.
  let { contacts, onopen, onadd, onremove } = $props();
</script>

<div class="vac-contacts-head">
  <span class="field-label">Контакты</span>
  <button class="add-link" type="button" onclick={onadd}>+ Контакт</button>
</div>

{#each contacts as one (one.id)}
  <div class="vac-contact">
    <button class="vac-contact-link" type="button" title="Открыть" onclick={() => onopen(one.value)}>
      {one.value}
    </button>
    <button class="remove-cross" type="button" title="Удалить контакт" onclick={() => onremove(one.id)}>
      ×
    </button>
  </div>
{/each}

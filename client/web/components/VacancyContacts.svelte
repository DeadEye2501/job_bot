<script>
  // Контакты вакансии, кроме Telegram-HR: подпись с «+ Контакт» и список, где
  // контакт по нажатию открывается или копируется и убирается крестиком.
  //
  // Что с контактом делать, решает тот, кто позвал: здесь только значение
  // строки. Копируемый (`copyable`) вида ссылки не носит — нажатие на него
  // никуда не ведёт.
  let { contacts, copyable, onopen, oncopy, onadd, onremove } = $props();
</script>

<div class="vac-contacts-head">
  <span class="field-label">Контакты</span>
  <button class="add-link" type="button" onclick={onadd}>+ Контакт</button>
</div>

{#each contacts as one (one.id)}
  {@const copied = copyable(one.value)}
  <div class="vac-contact">
    <button
      class="vac-contact-link"
      class:link-hover={!copied}
      type="button"
      title={copied ? 'Скопировать' : 'Открыть'}
      onclick={() => (copied ? oncopy : onopen)(one.value)}
    >
      {one.value}
    </button>
    <button class="remove-cross" type="button" title="Удалить контакт" onclick={() => onremove(one.id)}>
      ×
    </button>
  </div>
{/each}

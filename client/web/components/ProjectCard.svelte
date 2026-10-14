<script>
  // Проект: поля карточки записи анкеты — название, ссылка, «О проекте», стек.
  import { projectTitle } from '$state/projects.js';

  import BulletList from './BulletList.svelte';
  import RecordCard from './RecordCard.svelte';
  import StackField from './StackField.svelte';

  // `missing` — пустые обязательные поля, из-за которых проект не сохранили.
  let { record, known, open, missing, ontoggle, onedit, onremove } = $props();

  const title = $derived(projectTitle(record));
</script>

<RecordCard {title} {open} {ontoggle} {onremove} removeLabel="Удалить проект">
  <div class="field-row">
    <input
      class="input"
      class:missing={missing.includes('name')}
      maxlength="255"
      placeholder="Название проекта"
      value={record.name}
      onblur={(event) => onedit({ name: event.currentTarget.value.trim() })}
    />
    <input
      class="input"
      maxlength="255"
      placeholder="Ссылка"
      value={record.url || ''}
      onblur={(event) => onedit({ url: event.currentTarget.value.trim() })}
    />
  </div>

  <BulletList
    label="О проекте"
    addLabel="Добавить пункт"
    items={record.about}
    onchange={(about) => onedit({ about })}
  />

  <StackField chosen={record.skill_names} {known} {onedit} />
</RecordCard>

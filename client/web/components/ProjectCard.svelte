<script>
  // Проект: поля карточки записи анкеты — название, ссылка, «О проекте», стек.
  import { projectTitle } from '$state/projects.js';

  import BulletList from './BulletList.svelte';
  import RecordCard from './RecordCard.svelte';
  import StackField from './StackField.svelte';

  let { record, known, open, ontoggle, onedit, onremove } = $props();

  const title = $derived(projectTitle(record));
</script>

<RecordCard {title} {open} {ontoggle} {onremove} removeLabel="Удалить проект">
  <div class="field-row">
    <input
      class="input"
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
    onedit={(index, text) =>
      onedit({ about: record.about.map((one, at) => (at === index ? text : one)) })}
    onadd={() => onedit({ about: [...record.about, ''] })}
    onremove={(index) => onedit({ about: record.about.filter((_, at) => at !== index) })}
  />

  <StackField chosen={record.skill_names} {known} {onedit} />
</RecordCard>

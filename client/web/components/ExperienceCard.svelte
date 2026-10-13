<script>
  // Место работы: поля карточки записи анкеты.
  import { untrack } from 'svelte';

  import { cardTitle } from '$state/experience.js';

  import BulletList from './BulletList.svelte';
  import DatePicker from './DatePicker.svelte';
  import RecordCard from './RecordCard.svelte';
  import StackField from './StackField.svelte';

  let { record, known, open, ontoggle, onedit, onremove } = $props();

  const title = $derived(cardTitle(record));

  // «Работаю сейчас» — это признак самой карточки, а не пустая дата окончания.
  // Выводи мы его из даты, снятая галочка тут же возвращалась бы: даты-то ещё
  // нет, человек только собирается её набрать.
  let current = $state(untrack(() => !record.end_date));

  function switchCurrent(on) {
    current = on;
    // Дату окончания стираем только при включении. При снятии не сочиняем
    // ничего: стёртую дату поле уже показало пустой — оно идёт за доводом, — и
    // человек вписывает в него свою.
    if (on) onedit({ end_date: null });
  }

  /** Принять выбранную дату.
   *
   * Стёртое поле уходит пустотой, а не пустой строкой: `null` мост понимает как
   * «даты нет», и им же стирает дату окончания галочка «по настоящее время».
   */
  function pickDate(key, iso) {
    onedit({ [key]: iso || null });
  }
</script>

<RecordCard {title} {open} {ontoggle} {onremove} removeLabel="Удалить место работы">
  <div class="field-row">
    <input
      class="input"
      maxlength="255"
      placeholder="Компания"
      value={record.company}
      onblur={(event) => onedit({ company: event.currentTarget.value.trim() })}
    />
    <input
      class="input"
      maxlength="255"
      placeholder="URL компании"
      value={record.company_url || ''}
      onblur={(event) => onedit({ company_url: event.currentTarget.value.trim() })}
    />
    <input
      class="input span-2"
      maxlength="120"
      placeholder="Должность"
      value={record.role || ''}
      onblur={(event) => onedit({ role: event.currentTarget.value.trim() })}
    />

    <div class="date-pair span-2">
      <DatePicker value={record.start_date} onpick={(iso) => pickDate('start_date', iso)} />
      <span class="date-dash">—</span>
      <DatePicker
        value={record.end_date}
        disabled={current}
        onpick={(iso) => pickDate('end_date', iso)}
      />
      <label class="date-current">
        <input
          type="checkbox"
          checked={current}
          onchange={(event) => switchCurrent(event.currentTarget.checked)}
        />
        по настоящее время
      </label>
    </div>
  </div>

  <BulletList
    label="Достижения"
    addLabel="Добавить достижение"
    items={record.achievements}
    onchange={(achievements) => onedit({ achievements })}
  />

  <BulletList
    label="Обязанности"
    addLabel="Добавить обязанность"
    items={record.responsibilities}
    onchange={(responsibilities) => onedit({ responsibilities })}
  />

  <StackField chosen={record.skill_names} {known} {onedit} />
</RecordCard>

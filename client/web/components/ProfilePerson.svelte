<script>
  // Строки анкеты справа от фото. Только раскладка. Однострочное поле рисует анкета (`field`): запись у неё
  // одна на всю страницу, и поле должно звать именно её.
  import ChoiceRow from './ChoiceRow.svelte';
  import DatePicker from './DatePicker.svelte';
  import Dropdown from './Dropdown.svelte';
  import { CURRENCIES, GENDERS, SALARY_PERIODS } from '$state/profile.js';

  // `onset` — значение ставится как есть; `onpickone` — одно из перечня, и
  // нажатое повторно снимается.
  let { form, field, onset, onpickone } = $props();

  const NAME_FIELDS = [
    { key: 'last_name', placeholder: 'Фамилия *', max: 64, must: true },
    { key: 'first_name', placeholder: 'Имя *', max: 64, must: true },
    { key: 'patronymic', placeholder: 'Отчество', max: 64 },
  ];
  const LATIN_FIELDS = [
    { key: 'last_name_latin', placeholder: 'Фамилия латиницей', max: 64 },
    { key: 'first_name_latin', placeholder: 'Имя латиницей', max: 64 },
    { key: 'patronymic_latin', placeholder: 'Отчество латиницей', max: 64 },
  ];
</script>

<div class="name-grid">
  {@render field({ key: 'title', placeholder: 'Должность *', max: 120, must: true })}

  <div class="input-pair">
    {#each NAME_FIELDS as one (one.key)}{@render field(one)}{/each}
  </div>
  <div class="input-pair">
    {#each LATIN_FIELDS as one (one.key)}{@render field(one)}{/each}
  </div>

  <div class="field-line">
    {@render field({ key: 'citizenship', placeholder: 'Гражданство', max: 120 })}
    <DatePicker value={form.birth_date} onpick={(iso) => onset('birth_date', iso)} />
    <ChoiceRow
      options={GENDERS}
      chosen={new Set([form.gender])}
      look="tile"
      onpick={(value) => onpickone('gender', value)}
    />
  </div>

  {@render field({ key: 'location', placeholder: 'Город', max: 120 })}

  <div class="field-line">
    {@render field({
      key: 'expected_salary',
      placeholder: 'Ожидаемая зарплата на руки',
      max: 12,
      mode: 'numeric',
    })}
    <div class="field-narrow">
      <Dropdown
        options={CURRENCIES}
        value={form.expected_salary_currency}
        placeholder="—"
        onpick={(sign) => onset('expected_salary_currency', sign)}
      />
    </div>
    <ChoiceRow
      options={SALARY_PERIODS}
      chosen={new Set([form.expected_salary_period])}
      look="seg"
      onpick={(value) => onpickone('expected_salary_period', value)}
    />
  </div>
</div>

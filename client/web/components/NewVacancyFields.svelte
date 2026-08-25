<script>
  // Поля новой вакансии: то, из чего собирается её строка в списке и карточка.
  //
  // Своим объявлением рядом с полями человека и компании: набор у формы один,
  // мост читает ровно эти ключи, и лежать третья форма должна там же, где две
  // соседних, — иначе подписи у них разъедутся молча.
  //
  // Компания и человек набираются с подсказкой, а не выбираются из списка:
  // вакансию заводят по объявлению, и той компании в базе обычно ещё нет.
  // Принятое имя уходит наверх целиком — там его либо узнают, либо заводят;
  // ходить за этим полю не положено. Принимают его отдельным нажатием: уход
  // из поля завёл бы карточку, которой человек не просил.
  //
  // Ряды выбора вместо ввода у грейда и формата: значения замкнуты перечнями,
  // и набранное руками мост всё равно отсеет — человек не узнал бы, почему
  // написанное им пропало.
  //
  // Черновик правится на месте: он приходит своим объектом от того, кто его
  // потом и отправит.
  import { alone } from '$state/chosen.js';
  import { GRADES, WORK_FORMATS } from '$state/profile.js';

  import ChoiceRow from './ChoiceRow.svelte';
  import DraftChips from './DraftChips.svelte';
  import DraftNotes from './DraftNotes.svelte';
  import SuggestInput from './SuggestInput.svelte';

  let { draft, options, oncompany, onhr } = $props();

  // Ряд отмечает то, что есть в наборе, а у вакансии значение одно: набор из
  // него — способ сказать ряду «отмечено вот это».
  const grade = $derived(new Set([draft.grade]));
  const remote = $derived(new Set([draft.remote]));
</script>

<input class="input" placeholder="Название (обязательно)" bind:value={draft.title} />

<SuggestInput
  value={draft.company_name}
  options={options.companies}
  placeholder="Компания"
  asked
  onsave={oncompany}
/>

<SuggestInput
  value={draft.hr_name}
  options={options.hrs}
  placeholder="HR"
  asked
  onsave={onhr}
/>

<input class="input" placeholder="Ссылка на объявление" bind:value={draft.source_url} />

<ChoiceRow
  options={GRADES}
  chosen={grade}
  look="seg"
  onpick={(value) => (draft.grade = alone(draft.grade, value))}
/>
<ChoiceRow
  options={WORK_FORMATS}
  chosen={remote}
  look="seg"
  onpick={(value) => (draft.remote = alone(draft.remote, value))}
/>

<!-- Вилка тремя полями: человек читает её в объявлении разложенной, и набирать
     её одной строкой значило бы просить его склеить то, что мост разберёт
     обратно. -->
<div class="field-line">
  <input class="input" inputmode="numeric" placeholder="От" bind:value={draft.salary_min} />
  <input class="input" inputmode="numeric" placeholder="До" bind:value={draft.salary_max} />
  <!-- Валюту набирают словом: «usd», «руб», «долларов» — приводит её мост тем
       же разбором, каким читает зарплату из объявления. -->
  <input class="input" placeholder="Валюта" bind:value={draft.salary_currency} />
</div>

<!-- Страна и город порознь: разбор объявления кладёт их одной строкой через
     косую черту, и складывает её мост — чтобы заведённое руками писалось так
     же, как найденное ботом. -->
<div class="field-line">
  <input class="input" placeholder="Страна" bind:value={draft.country} />
  <input class="input" placeholder="Город" bind:value={draft.city} />
</div>

<DraftChips {draft} field="stack" caption="Скилы:" />

<textarea class="textarea" placeholder="Описание" bind:value={draft.description}></textarea>
<DraftNotes {draft} />

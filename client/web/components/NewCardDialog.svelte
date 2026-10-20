<script>
  // Окно заведения карточки — человека, компании или вакансии.
  //
  // Своим объявлением, потому что окон таких четыре: «Добавить» на вкладке
  // людей, то же на вкладке компаний, заведение на ходу из подборщика связи
  // вакансии и «Добавить вакансию» над её списком. Слова у них общие
  // (`state/new_card.js`), а обвязка была написана в каждом своя — и
  // разъезжаться теперь стала бы она.
  //
  // Набор полей выбирается здесь по роду: снаружи он и так не нужен никому,
  // кроме этого окна, а выбор в трёх местах разошёлся бы так же, как слова.
  //
  // Черновик приходит своим объектом и правится на месте: отправляет его тот,
  // кто его завёл.
  import { NEW_CARD } from '$state/new_card.js';
  import { VACANCY_MODES, isText } from '$state/vacancies.js';

  import AskDialog from './AskDialog.svelte';
  import ChoiceRow from './ChoiceRow.svelte';
  import NewCompanyFields from './NewCompanyFields.svelte';
  import NewPersonFields from './NewPersonFields.svelte';
  import NewVacancyFields from './NewVacancyFields.svelte';
  import PastedVacancyFields from './PastedVacancyFields.svelte';
  import RowToggle from './RowToggle.svelte';

  // Подсказки и приём набранного нужны одной форме из трёх — вакансии: она
  // называет компанию и человека словами, а узнаёт их и заводит тот, кто
  // держит мост. У человека и компании подсказывать нечему.
  //
  // `locked` — почему заводить сейчас нельзя; пусто — можно. Кнопка заперта и
  // говорит причину своей подписью, как говорит, что работа идёт.
  //
  // `toggle` — «Отклик при создании» у вакансии готовым видом (`sourceToggle`):
  // положение, запор и подсказка; `ontoggle(next)` его переключает.
  let {
    kind,
    draft,
    busy,
    ready,
    locked = '',
    options = null,
    toggle = null,
    ontoggle = null,
    oncompany = null,
    onhr = null,
    onconfirm,
    oncancel,
  } = $props();

  const form = $derived(NEW_CARD[kind]);
</script>

<AskDialog
  icon={form.icon}
  extra={kind === 'vacancy' ? 'tall' : ''}
  title={form.title}
  confirmLabel="Создать"
  busyLabel={locked || form.busyLabel}
  busy={busy || Boolean(locked)}
  {ready}
  {onconfirm}
  {oncancel}
>
  {#if kind === 'hr'}
    <NewPersonFields {draft} />
  {:else if kind === 'company'}
    <NewCompanyFields {draft} />
  {:else}
    <!-- Ряд способов только у вакансии: её заводят двумя — набирают поля сами
         или отдают боту текст объявления. У человека и компании второго нет
         вовсе. Ряд тот же, что у грейда и формата: свой разошёлся бы с ними
         видом. -->
    <div class="choice-line">
      <ChoiceRow
        options={VACANCY_MODES}
        chosen={new Set([draft.mode])}
        look="seg"
        onpick={(value) => (draft.mode = value)}
      />
      <RowToggle
        look="box"
        checked={toggle.checked}
        disabled={toggle.disabled}
        title={toggle.title}
        {ontoggle}
      />
    </div>
    {#if isText(draft)}
      <PastedVacancyFields {draft} />
    {:else}
      <NewVacancyFields {draft} {options} {oncompany} {onhr} />
    {/if}
  {/if}
</AskDialog>

<script>
  // Окно заведения карточки контакта — человека или компании.
  //
  // Своим объявлением, потому что окон таких три: «Добавить» на вкладке людей,
  // то же на вкладке компаний и заведение на ходу из подборщика связи вакансии.
  // Слова у них давно общие (`state/new_card.js`), а обвязка была написана
  // трижды — и разъезжаться теперь стала бы она.
  //
  // Набор полей выбирается здесь по роду: снаружи он и так не нужен никому,
  // кроме этого окна, а выбор в трёх местах разошёлся бы так же, как слова.
  //
  // Черновик приходит своим объектом и правится на месте: отправляет его тот,
  // кто его завёл.
  import { NEW_CARD } from '$state/new_card.js';

  import AskDialog from './AskDialog.svelte';
  import NewCompanyFields from './NewCompanyFields.svelte';
  import NewPersonFields from './NewPersonFields.svelte';

  let { kind, draft, busy, ready, onconfirm, oncancel } = $props();

  const form = $derived(NEW_CARD[kind]);
</script>

<AskDialog
  icon={form.icon}
  title={form.title}
  subtitle={form.subtitle}
  confirmLabel="Создать"
  busyLabel={form.busyLabel}
  {busy}
  {ready}
  {onconfirm}
  {oncancel}
>
  {#if kind === 'hr'}
    <NewPersonFields {draft} />
  {:else}
    <NewCompanyFields {draft} />
  {/if}
</AskDialog>

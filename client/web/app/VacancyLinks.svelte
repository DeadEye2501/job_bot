<script>
  // Связи вакансии: кого к ней привязать и кого завести, если нужного ещё нет.
  //
  // Путь один для человека и для компании — подборщик, а из него окно
  // заведения, — а различаются они предметом: методом моста, полями формы и
  // строкой списка. Зовы моста написаны литералами в обеих ветках: имя метода
  // должно быть видно на шве, а собранное из кусков там не видно вовсе.
  //
  // Заведённый возвращается в список отмеченным, но не привязанным: заведение и
  // привязка — разные решения, и второе человек принимает сам.
  import AskDialog from '$components/AskDialog.svelte';
  import NewCompanyFields from '$components/NewCompanyFields.svelte';
  import NewPersonFields from '$components/NewPersonFields.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import { blankCompany, companyCandidate, companyNamed } from '$state/companies.js';
  import { blankPerson, named, personCandidate } from '$state/people.js';

  let { ask, say, vacancyId, kind, prefill = '', current = null, onclose, onlinked } = $props();

  // Поля заведения у человека и у компании разные, и берутся они там же, где их
  // берут вкладки контактов: мост читает ровно эти.
  const BLANK = { hr: blankPerson, company: blankCompany };

  let creating = $state(false);
  let saving = $state(false);
  let picked = $state(null);
  // Свой набор полей на каждый род: окно открывают то для человека, то для
  // компании, и один набор на двоих уехал бы на мост с чужими ключами.
  let drafts = $state({ hr: blankPerson(), company: blankCompany() });
  const draft = $derived(drafts[kind]);

  // Заслон тот же, что в списках контактов: человеку — хоть что-нибудь из трёх,
  // компании — название.
  const ready = $derived(kind === 'hr' ? named(draft) : companyNamed(draft));

  async function candidates(search) {
    const now =
      kind === 'hr'
        ? await ask('vacancies.hr_picker', { vacancy_id: vacancyId, search })
        : await ask('vacancies.company_picker', { vacancy_id: vacancyId, search });
    if (now === null) return null;
    return kind === 'hr' ? now.hrs : now.companies;
  }

  async function link(row) {
    saving = true;
    const done =
      kind === 'hr'
        ? await ask('vacancies.link_hr', { vacancy_id: vacancyId, hr_id: row.id })
        : await ask('vacancies.link_company', { vacancy_id: vacancyId, company_id: row.id });
    saving = false;
    if (done === null) return;
    say(kind === 'hr' ? 'HR привязан' : 'Компания привязана');
    onlinked();
    onclose();
  }

  /** Завести нового и вернуться к списку с отметкой на нём.
   *
   * Пустое не отправляется вовсе — теми же заслонами, что и в списках
   * контактов: без имени карточку потом не найти ничем, и мост такую всё равно
   * отобьёт. Повторное нажатие, пока летит первое, завело бы двоих.
   */
  async function create() {
    if (saving) return;
    if (!ready) return;
    saving = true;
    const done =
      kind === 'hr'
        ? await ask('vacancies.create_hr', { vacancy_id: vacancyId, ...draft })
        : await ask('vacancies.create_company', { vacancy_id: vacancyId, ...draft });
    saving = false;
    // Отказ форму не закрывает: набранное осталось бы набирать заново, а мост
    // уже сказал плашкой, чего ему не хватило.
    if (done === null) return;
    creating = false;
    drafts[kind] = BLANK[kind]();
    say(kind === 'hr' ? 'Человек заведён' : 'Компания заведена');
    picked = done.created_id;
  }
</script>

{#if creating}
  <AskDialog
    icon={kind === 'hr' ? 'person_add' : 'add_business'}
    title={kind === 'hr' ? 'Новый HR' : 'Новая компания'}
    confirmLabel="Создать"
    {ready}
    onconfirm={create}
    oncancel={() => (creating = false)}
  >
    {#if kind === 'hr'}
      <NewPersonFields {draft} />
    {:else}
      <NewCompanyFields {draft} />
    {/if}
  </AskDialog>
{:else}
  <PickerDialog
    icon={kind === 'hr' ? 'person_search' : 'domain'}
    title={kind === 'hr' ? 'Связать с HR' : 'Связать с компанией'}
    placeholder={kind === 'hr'
      ? 'Поиск по имени, @username...'
      : 'Поиск по названию, сайту, алиасам...'}
    empty={kind === 'hr' ? 'HR-контактов пока нет' : 'Компаний пока нет'}
    {prefill}
    {current}
    preselect={picked}
    load={candidates}
    applyLabel="Связать"
    onapply={link}
    {saving}
    createIcon={kind === 'hr' ? 'person_add' : 'add_business'}
    createLabel={kind === 'hr' ? 'Создать нового HR' : 'Создать новую компанию'}
    oncreate={() => (creating = true)}
    {onclose}
  >
    {#snippet children(rows, chosen, pick)}
      {#each rows as row (row.id)}
        <PickerRow
          row={kind === 'hr' ? personCandidate(row) : companyCandidate(row)}
          current={row.id === current}
          chosen={row.id === chosen}
          mark={kind === 'hr' ? 'текущий' : 'текущая'}
          onpick={pick}
        />
      {/each}
    {/snippet}
  </PickerDialog>
{/if}

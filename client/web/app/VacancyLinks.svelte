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
  import NewCardDialog from '$components/NewCardDialog.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import PickerRow from '$components/PickerRow.svelte';
  import { companyCandidate } from '$state/companies.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { personCandidate } from '$state/people.js';

  let { ask, say, vacancyId, kind, prefill = '', current = null, onclose, onlinked } = $props();

  // Обвязка формы заведения — общая со вкладками контактов: форма одна, а окон
  // два, и разъехавшиеся слова уже стоили этому окну своего заголовка.
  const FORM = $derived(NEW_CARD[kind]);

  let creating = $state(false);
  let saving = $state(false);
  let picked = $state(null);
  // Свой набор полей на каждый род: окно открывают то для человека, то для
  // компании, и один набор на двоих уехал бы на мост с чужими ключами.
  let drafts = $state({ hr: NEW_CARD.hr.blank(), company: NEW_CARD.company.blank() });
  const draft = $derived(drafts[kind]);

  // Заслон тот же, что в списках контактов: человеку — хоть что-нибудь из трёх,
  // компании — название.
  const ready = $derived(FORM.named(draft));

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
   * отобьёт. От второго нажатия, пока летит первое, держит само окно: `busy`
   * запирает кнопку, и свой заслон здесь был бы вторым по тому же поводу.
   */
  async function create() {
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
    drafts[kind] = FORM.blank();
    say(FORM.done);
    picked = done.created_id;
  }
</script>

{#if creating}
  <NewCardDialog
    {kind}
    {draft}
    busy={saving}
    {ready}
    onconfirm={create}
    oncancel={() => (creating = false)}
  />
{:else}
  <PickerDialog
    icon={kind === 'hr' ? 'person_search' : 'domain'}
    title={kind === 'hr' ? 'Связать с HR' : 'Связать с компанией'}
    placeholder={FORM.searchHint}
    empty={kind === 'hr' ? 'HR-контактов пока нет' : 'Компаний пока нет'}
    {prefill}
    {current}
    preselect={picked}
    load={candidates}
    applyLabel="Связать"
    onapply={link}
    {saving}
    createIcon={FORM.icon}
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

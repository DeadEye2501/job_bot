<script>
  // Связи вакансии: кого к ней привязать и кого завести, если нужного ещё нет.
  //
  // Путь один для человека и для компании — подборщик, а из него окно
  // заведения, — а различаются они предметом: методом моста, полями формы и
  // строкой списка. Зовы моста написаны литералами в обеих ветках: имя метода
  // должно быть видно на шве, а собранное из кусков там не видно вовсе.
  //
  // Заведённого привязываем сразу: человек пришёл сюда за привязкой, и второе
  // нажатие после заполненной формы ничего не решает.
  import AskDialog from '$components/AskDialog.svelte';
  import CompanyRow from '$components/CompanyRow.svelte';
  import NewCompanyFields from '$components/NewCompanyFields.svelte';
  import NewPersonFields from '$components/NewPersonFields.svelte';
  import PersonRow from '$components/PersonRow.svelte';
  import PickerDialog from '$components/PickerDialog.svelte';
  import { named } from '$state/contacts.js';

  let { ask, say, vacancyId, kind, onclose, onlinked } = $props();

  // Поля заведения у человека и у компании разные, и лишних не заводится: мост
  // читает ровно эти.
  const BLANK = {
    hr: { name: '', telegram_username: '', telegram_user_id: '', notes: '' },
    company: { name: '', website: '', aliases: '', notes: '' },
  };

  let creating = $state(false);
  let saving = $state(false);
  let draft = $state({ ...BLANK[kind] });

  async function candidates(search) {
    const now =
      kind === 'hr'
        ? await ask('vacancies.hr_picker', { vacancy_id: vacancyId, search })
        : await ask('vacancies.company_picker', { vacancy_id: vacancyId, search });
    if (now === null) return null;
    return kind === 'hr' ? now.hrs : now.companies;
  }

  async function link(id) {
    const done =
      kind === 'hr'
        ? await ask('vacancies.link_hr', { vacancy_id: vacancyId, hr_id: id })
        : await ask('vacancies.link_company', { vacancy_id: vacancyId, company_id: id });
    if (done === null) return;
    say(kind === 'hr' ? 'HR привязан' : 'Компания привязана');
    onlinked();
    onclose();
  }

  /** Завести нового и тут же привязать.
   *
   * Пустое не отправляется вовсе — теми же заслонами, что и в списках
   * контактов: без имени карточку потом не найти ничем, и мост такую всё равно
   * отобьёт. Повторное нажатие, пока летит первое, завело бы двоих.
   */
  async function create() {
    if (saving) return;
    if (kind === 'hr' ? !named(draft) : !draft.name.trim()) return;
    saving = true;
    const done =
      kind === 'hr'
        ? await ask('vacancies.create_hr', { vacancy_id: vacancyId, ...draft })
        : await ask('vacancies.create_company', { vacancy_id: vacancyId, ...draft });
    saving = false;
    // Отказ форму не закрывает: набранное осталось бы набирать заново, а мост
    // уже сказал плашкой, чего ему не хватило.
    if (done === null) return;
    // Заведённый уже есть, и форму надо закрыть до привязки: сорвись она —
    // повторное нажатие по той же форме завело бы второго.
    creating = false;
    return link(done.created_id);
  }
</script>

{#if creating}
  <AskDialog
    icon={kind === 'hr' ? 'person_add' : 'domain_add'}
    title={kind === 'hr' ? 'Новый человек' : 'Новая компания'}
    subtitle={kind === 'hr'
      ? 'Хотя бы имя, ник или номер учётной записи — иначе карточку потом не найти.'
      : 'Название обязательно, остальное можно дописать потом.'}
    confirmLabel="Завести и привязать"
    onconfirm={create}
    oncancel={() => (creating = false)}
  >
    {#if kind === 'hr'}
      <NewPersonFields {draft} onenter={create} />
    {:else}
      <NewCompanyFields {draft} onenter={create} />
    {/if}
  </AskDialog>
{:else}
  <PickerDialog
    icon="link"
    title={kind === 'hr' ? 'Связать с HR' : 'Связать с компанией'}
    placeholder={kind === 'hr'
      ? 'Поиск по имени и нику'
      : 'Поиск по названию, написанию, домену'}
    words={kind === 'hr'
      ? ['человек', 'человека', 'человек']
      : ['компания', 'компании', 'компаний']}
    empty={kind === 'hr' ? 'Людей ещё нет' : 'Компаний ещё нет'}
    load={candidates}
    {onclose}
  >
    {#snippet children(rows)}
      {#each rows as row (row.id)}
        {#if kind === 'hr'}
          <PersonRow person={row} onpick={() => link(row.id)} />
        {:else}
          <CompanyRow company={row} onpick={() => link(row.id)} />
        {/if}
      {/each}
    {/snippet}

    {#snippet extra()}
      <button class="btn" type="button" onclick={() => (creating = true)}>
        <span class="material-symbols-outlined">{kind === 'hr' ? 'person_add' : 'domain_add'}</span>
        {kind === 'hr' ? 'Новый человек' : 'Новая компания'}
      </button>
    {/snippet}
  </PickerDialog>
{/if}

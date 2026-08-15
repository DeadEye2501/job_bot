<script>
  // Вкладка «Компании»: список слева, карточка выбранной справа.

  import { untrack } from 'svelte';

  import AskDialog from '$components/AskDialog.svelte';
  import NewCompanyFields from '$components/NewCompanyFields.svelte';
  import CompanyRow from '$components/CompanyRow.svelte';
  import SearchBox from '$components/SearchBox.svelte';
  import { attempts } from '$state/attempts.js';
  import { PAGE, appended, nearBottom, refreshLimit } from '$state/paging.js';

  import CompanyCard from './CompanyCard.svelte';

  let { ask, say, events, open, onopened, onperson, onvacancy } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let hasMore = $state(false);
  let search = $state('');
  let adding = $state(false);
  let draft = $state({ name: '', website: '', aliases: '', notes: '' });

  // Без названия заводить нечего: мост такую компанию всё равно отобьёт, а
  // человек прочитает отказ вместо заведённой карточки.
  const ready = $derived(Boolean(draft.name.trim()));
  let opened = $state(null);
  let loadingMore = $state(false);

  const tries = attempts();
  let alive = true;

  // Какую компанию открыть, придя из карточки вакансии. Отметка гасится сразу:
  // вкладку открывают и просто так, и заново открытая карточка компании,
  // которую уже закрыли, читалась бы как поломка.
  $effect(() => {
    if (!open) return;
    opened = open.id;
    onopened();
  });

  /** Перечитать список с начала.
   *
   * Человек набирает поиск посимвольно, ответы приходят вразнобой, и лёгший
   * поверх свежего старый показал бы строки, которых он уже не ищет. Отсюда
   * счёт попыток: пришедший на прежний вопрос ответ не считается.
   *
   * Потолок — довод, потому что перечитывают этот список и после правки в
   * карточке: там показанного бывает больше страницы.
   */
  async function refresh(limit = PAGE) {
    const mine = tries.next();
    const now = await ask('companies.list', { search, limit, offset: 0 });
    if (now === null || !alive || tries.stale(mine)) return;
    rows = now.companies;
    hasMore = now.has_more;
    loaded = true;
  }

  /** Дочитать следующую страницу.
   *
   * Своей попыткой, а не под чужой: страница, доехавшая после смены поиска,
   * дописала бы в список чужие строки.
   */
  async function more() {
    const mine = tries.next();
    const page = await ask('companies.list', { search, limit: PAGE, offset: rows.length });
    if (page === null || !alive || tries.stale(mine)) return;
    rows = appended(rows, page.companies);
    hasMore = page.has_more;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  /** Дочитать следующую страницу, когда список подошёл к концу.
   *
   * Прокруткой, а не кнопкой: список читают сверху вниз и глазами, а кнопка
   * посреди чтения заставляет целиться в неё мышью.
   */
  function scrolled(event) {
    if (!hasMore || loadingMore || !nearBottom(event.currentTarget)) return;
    loadingMore = true;
    more().finally(() => {
      loadingMore = false;
    });
  }

  async function create() {
    const name = draft.name.trim();
    if (!ready) return;
    const done = await ask('companies.create', { ...draft, name });
    // Окно закрываем только по удаче: чаще всего отказ — это занятое имя, и
    // набранное человеку ещё пригодится.
    if (done === null) return;
    adding = false;
    draft = { name: '', website: '', aliases: '', notes: '' };
    say('Компания заведена');
    // Тем же потолком, что и по вести: заведение не повод схлопывать
    // пролистанное.
    return refresh(refreshLimit(rows.length));
  }

  $effect(() => {
    alive = true;
    // Списки меняет не только этот экран: бот заводит компании сам, разбирая
    // объявления. Без этой подписки экран показывал бы снимок той минуты,
    // когда его открыли.
    // Перечитываем по вести не страницей, а показанным: иначе занесение в
    // отсев из карточки схлопывало бы пролистанное до первой страницы.
    const deaf = events.on('contacts_lists_changed', () => refresh(refreshLimit(rows.length)));
    // Первое чтение — вне слежения: строку поиска `refresh` читает, и следящий
    // эффект перезаводился бы на каждом набранном знаке — вместе с подпиской и
    // вторым, никому не нужным вопросом мосту.
    untrack(() => refresh());
    return () => {
      alive = false;
      deaf();
    };
  });
</script>

<div class="cnt-layout">
  <section class="cnt-list-pane">
    <div class="cnt-list-toolbar">
      <SearchBox
        value={search}
        placeholder="Поиск по названию, алиасу, домену..."
        onsearch={find}
      />
      <button
        class="cnt-add-btn"
        type="button"
        title="Добавить компанию"
        onclick={() => (adding = true)}
      >
        <span class="material-symbols-outlined">add_business</span>
      </button>
    </div>

    <div class="cnt-list" onscroll={scrolled}>
      {#if !loaded}
        <div class="cnt-list-empty">Загрузка…</div>
      {:else if rows.length === 0}
        <div class="cnt-list-empty">
          {#if search}
            Ничего не найдено по запросу «{search}»
          {:else}
            Компаний пока нет
          {/if}
        </div>
      {:else}
        {#each rows as company (company.id)}
          <CompanyRow
            {company}
            selected={opened === company.id}
            onpick={() => (opened = company.id)}
          />
        {/each}
      {/if}
    </div>
  </section>

  <section class="cnt-detail-pane">
    {#if opened === null}
      <div class="cnt-detail-empty">Выберите компанию в списке слева</div>
    {:else}
      <CompanyCard
        {ask}
        {say}
        {onperson}
        {onvacancy}
        companyId={opened}
        onclose={() => (opened = null)}
        onchanged={() => refresh(refreshLimit(rows.length))}
      />
    {/if}
  </section>
</div>

{#if adding}
  <AskDialog
    icon="domain_add"
    title="Новая компания"
    subtitle="Название обязательно, остальное можно дописать потом."
    confirmLabel="Создать"
    {ready}
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <NewCompanyFields {draft} />
  </AskDialog>
{/if}

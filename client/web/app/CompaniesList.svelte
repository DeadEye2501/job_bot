<script>
  // Вкладка «Компании»: список с поиском, страницами и заведением.

  import { untrack } from 'svelte';

  import AskDialog from '$components/AskDialog.svelte';
  import CompanyRow from '$components/CompanyRow.svelte';
  import SearchList from '$components/SearchList.svelte';
  import { attempts } from '$state/attempts.js';
  import { PAGE, appended, refreshLimit } from '$state/paging.js';

  import CompanyCard from './CompanyCard.svelte';

  let { ask, say, events } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let hasMore = $state(false);
  let search = $state('');
  let adding = $state(false);
  let draft = $state({ name: '', website: '', aliases: '', notes: '' });
  let opened = $state(null);

  const tries = attempts();
  let alive = true;

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

  async function create() {
    const name = draft.name.trim();
    if (!name) return;
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

<SearchList
  {search}
  placeholder="Поиск по названию, написанию, домену"
  onsearch={find}
  {loaded}
  count={rows.length}
  words={['компания', 'компании', 'компаний']}
  empty={search ? 'Ничего не найдено' : 'Компаний пока нет'}
>
  {#snippet actions()}
    <button class="btn primary" type="button" onclick={() => (adding = true)}>
      <span class="material-symbols-outlined">add</span>
      Компания
    </button>
  {/snippet}

  {#each rows as company (company.id)}
    <CompanyRow {company} onpick={() => (opened = company.id)} />
  {/each}

  {#if hasMore}
    <button class="add-more" type="button" onclick={more}>Показать ещё</button>
  {/if}
</SearchList>

{#if adding}
  <AskDialog
    icon="domain_add"
    title="Новая компания"
    subtitle="Название обязательно, остальное можно дописать потом."
    confirmLabel="Создать"
    onconfirm={create}
    oncancel={() => (adding = false)}
  >
    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="input"
      autofocus
      placeholder="Название"
      bind:value={draft.name}
      onkeydown={(event) => event.key === 'Enter' && create()}
    />
    <input class="input" placeholder="Сайт или домен" bind:value={draft.website} />
    <input class="input" placeholder="Другие написания через запятую" bind:value={draft.aliases} />
    <textarea class="textarea" placeholder="Заметки" bind:value={draft.notes}></textarea>
  </AskDialog>
{/if}

{#if opened}
  <CompanyCard
    {ask}
    {say}
    companyId={opened}
    onclose={() => (opened = null)}
    onchanged={() => refresh(refreshLimit(rows.length))}
  />
{/if}

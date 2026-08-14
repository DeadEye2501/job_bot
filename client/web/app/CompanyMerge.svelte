<script>
  // Окно слияния: в какую компанию влить эту.
  //
  // Список тот же, что во вкладке, но без поглощаемой: влить карточку в саму
  // себя нельзя, а показанная строка выглядела бы разрешённым выбором. Убирает
  // её мост — здесь она не отсеивается второй раз.

  import { untrack } from 'svelte';

  import CompanyRow from '$components/CompanyRow.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import SearchList from '$components/SearchList.svelte';
  import { attempts } from '$state/attempts.js';
  import { companyLine } from '$state/companies.js';

  let { ask, absorbedId, absorbedName, onclose, onmerged } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let search = $state('');
  let chosen = $state(null);

  const tries = attempts();
  let alive = true;

  const chosenName = $derived(chosen ? companyLine(chosen).name : '');

  /** Перечитать кандидатов.
   *
   * Свежесть — своим счётом попыток: ответ на прежний набор в поле поиска уже
   * не про то, что человек ищет. Эхо строки поиска для этого не годится — мост
   * обрезает у неё края, и набранный пробел объявил бы устаревшим каждый ответ.
   */
  async function refresh() {
    const mine = tries.next();
    const now = await ask('companies.merge_picker', { absorbed_id: absorbedId, search });
    if (now === null || !alive || tries.stale(mine)) return;
    rows = now.companies;
    loaded = true;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  async function apply() {
    const survivor = chosen;
    chosen = null;
    const done = await ask('companies.merge', {
      absorbed_id: absorbedId,
      survivor_id: survivor.id,
    });
    if (done === null) return;
    onmerged();
  }

  $effect(() => {
    alive = true;
    // Вне слежения по тому же доводу, что и в списке: строку поиска `refresh`
    // читает, и эффект перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      alive = false;
    };
  });
</script>

<div class="modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && onclose()}>
  <div class="modal-dialog card-dialog" role="dialog" aria-modal="true">
    <div class="modal-title">
      <span class="material-symbols-outlined">merge</span>
      Слить «{absorbedName}» с другой
    </div>

    <SearchList
      {search}
      placeholder="Поиск по названию, написанию, домену"
      onsearch={find}
      {loaded}
      count={rows.length}
      words={['компания', 'компании', 'компаний']}
      filtered={!!search}
      nothing="Ничего не найдено"
      empty="Других компаний нет"
    >
      {#each rows as company (company.id)}
        <CompanyRow {company} onpick={() => (chosen = company)} />
      {/each}
    </SearchList>

    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
    </div>
  </div>
</div>

{#if chosen}
  <ConfirmDialog
    message={`Слить «${absorbedName}» в «${chosenName}»?\n\nВакансии перейдут к выбранной. Написания объединятся — нынешнее имя станет одним из них. Заметки склеятся. Сайт возьмётся у выбранной, а если его там нет — у нынешней. Эта компания будет удалена. Откатить нельзя.`}
    confirmLabel="Слить"
    onconfirm={apply}
    oncancel={() => (chosen = null)}
  />
{/if}

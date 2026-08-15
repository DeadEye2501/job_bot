<script>
  // Окно выбора из списка: кого искали, того и выбрали.
  //
  // Выбирают в трёх местах — с кем слить человека, с кем слить компанию, кого
  // привязать к вакансии, — и различаются они предметом, а не окном: поиск,
  // список кандидатов и выбор у них одни. Строки приходят снаружи разметкой, а
  // сам вопрос мосту — доводом `load`: имя метода остаётся литералом там, где
  // его знают, и не прячется от шва.
  //
  // Выбранного дальше ведёт зовущий: слияние спрашивает подтверждение, привязка
  // делается сразу, и знает об этом карточка, а не это окно.
  import { untrack } from 'svelte';

  import { attempts } from '$state/attempts.js';

  import ModalKeys from './ModalKeys.svelte';
  import SearchList from './SearchList.svelte';

  let { title, icon, placeholder, words, empty, load, onclose, children, extra = null } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let search = $state('');

  const tries = attempts();
  let alive = true;

  /** Перечитать кандидатов.
   *
   * Свежесть — своим счётом попыток: ответ на прежний набор в поле поиска уже
   * не про то, что человек ищет. Эхо строки поиска для этого не годится — мост
   * обрезает у неё края, и набранный пробел объявил бы устаревшим каждый ответ.
   */
  async function refresh() {
    const mine = tries.next();
    const now = await load(search);
    if (now === null || !alive || tries.stale(mine)) return;
    rows = now;
    loaded = true;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  $effect(() => {
    alive = true;
    // Вне слежения: строку поиска читает `refresh`, и следящий эффект
    // перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      alive = false;
    };
  });
</script>

<ModalKeys close={onclose} />

<div class="modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && onclose()}>
  <div class="modal-dialog card-dialog" role="dialog" aria-modal="true">
    <div class="modal-title">
      <span class="material-symbols-outlined">{icon}</span>
      {title}
    </div>

    <SearchList
      {search}
      {placeholder}
      onsearch={find}
      {loaded}
      count={rows.length}
      {words}
      filtered={!!search}
      nothing="Ничего не найдено"
      {empty}
    >
      {@render children(rows)}
    </SearchList>

    <div class="modal-actions">
      {#if extra}{@render extra()}{/if}
      <button class="btn" type="button" onclick={() => onclose()}>Закрыть</button>
    </div>
  </div>
</div>

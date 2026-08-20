<script>
  // Окно выбора из списка: кого искали, того и отметили.
  //
  // Выбирают в трёх местах — с кем слить человека, с кем слить компанию, кого
  // привязать к вакансии, — и различаются они предметом, а не окном: поиск,
  // список кандидатов и выбор у них одни. Строки приходят снаружи разметкой, а
  // сам вопрос мосту — доводом `load`: имя метода остаётся литералом там, где
  // его знают, и не прячется от шва.
  //
  // Выбор двухшаговый: нажатие по строке только помечает её, а делает дело
  // кнопка внизу. Промах мышью иначе менял бы привязку молча, а откатить это
  // нечем.
  import { untrack } from 'svelte';

  import { attempts } from '$state/attempts.js';
  import { linkReady } from '$state/picker.js';

  import ModalKeys from './ModalKeys.svelte';

  let {
    title,
    icon,
    placeholder,
    empty,
    prefill = '',
    current = null,
    preselect = null,
    load,
    applyLabel,
    onapply,
    saving = false,
    onclose,
    children,
    createLabel = null,
    createIcon = null,
    oncreate = null,
  } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let search = $state(prefill);
  let chosen = $state(null);

  const ready = $derived(linkReady({ current, chosen }));

  const tries = attempts();
  let alive = true;

  /** Перечитать кандидатов.
   *
   * Свежесть — своим счётом попыток: ответ на прежний набор в поле поиска уже
   * не про то, что человек ищет. Эхо строки поиска для этого не годится — мост
   * обрезает у неё края, и набранный пробел объявил бы устаревшим каждый ответ.
   *
   * Отметка с пропавшей из выдачи строки снимается: связывать невидимую строку
   * человек не просил, а кнопка внизу осталась бы отпертой.
   */
  async function refresh() {
    const mine = tries.next();
    const now = await load(search);
    if (now === null || !alive || tries.stale(mine)) return;
    rows = now;
    loaded = true;
    if (chosen !== null && !rows.some((one) => one.id === chosen)) chosen = null;
  }

  function find(text) {
    search = text;
    return refresh();
  }

  /** Отметить строку. Повторное нажатие снимает отметку: передумавшему иначе
   *  пришлось бы закрывать окно. */
  function pick(id) {
    chosen = chosen === id ? null : id;
  }

  function apply() {
    const row = rows.find((one) => one.id === chosen);
    if (row !== undefined) onapply(row);
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

  $effect(() => {
    // Завели нового — он должен появиться в списке и быть отмеченным. Связывает
    // человек сам, отдельным нажатием: заведение и привязка — разные решения.
    if (preselect === null) return;
    chosen = preselect;
    untrack(() => refresh());
  });
</script>

<ModalKeys close={onclose} />

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(event) => event.target === event.currentTarget && onclose()}
>
  <div class="modal-dialog vac-picker-modal" role="dialog" aria-modal="true">
    <div class="modal-head">
      <span class="material-symbols-outlined">{icon}</span>
      <div class="modal-title">{title}</div>
      <button class="modal-close" type="button" title="Закрыть" onclick={() => onclose()}>
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>

    <div class="picker-search-bar">
      <span class="material-symbols-outlined">search</span>
      <input
        type="text"
        {placeholder}
        value={search}
        oninput={(event) => find(event.currentTarget.value)}
      />
    </div>

    <div class="picker-list">
      {#if !loaded}
        <div class="picker-empty">Загрузка…</div>
      {:else if rows.length === 0}
        <!-- Пустых слов два, и разница несущая: «ничего не найдено» говорит, что
             список есть, а показать из него нечего, — и человек ищет причину в
             поле поиска, а не в том, что заводить он ещё ничего не начинал. -->
        <div class="picker-empty">
          {search ? `Ничего не найдено по запросу «${search}»` : empty}
        </div>
      {:else}
        {@render children(rows, chosen, pick)}
      {/if}
    </div>

    {#if oncreate}
      <div class="picker-create">
        <button class="picker-create-toggle" type="button" onclick={() => oncreate()}>
          <span class="material-symbols-outlined">{createIcon}</span>
          {createLabel}
        </button>
      </div>
    {/if}

    <div class="modal-footer">
      <button class="btn" type="button" onclick={() => onclose()}>Отмена</button>
      <button class="btn primary" type="button" disabled={saving || !ready} onclick={apply}>
        {saving ? 'Сохраняю…' : applyLabel}
      </button>
    </div>
  </div>
</div>

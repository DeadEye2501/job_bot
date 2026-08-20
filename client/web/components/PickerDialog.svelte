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

  import { living } from '$state/alive.js';
  import { freshAnswer } from '$state/fresh.js';
  import { linkReady } from '$state/picker.js';

  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';
  import SearchBox from './SearchBox.svelte';

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
    // Переименовано при разборе доводов: внутри рамы своё место для разметки
    // тоже зовётся `children`, и одно имя закрыло бы другое.
    children: rowsMarkup,
    createLabel = null,
    createIcon = null,
    oncreate = null,
  } = $props();

  let loaded = $state(false);
  let rows = $state([]);
  let search = $state(untrack(() => prefill));
  let chosen = $state(null);

  const ready = $derived(linkReady({ current, chosen }));

  const alive = living();
  const fresh = freshAnswer(() => alive.now);

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
    const now = await fresh(() => load(search));
    if (now === null) return;
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
    const settled = alive.mounted();
    // Вне слежения: строку поиска читает `refresh`, и следящий эффект
    // перезаводился бы на каждом набранном знаке.
    untrack(() => refresh());
    return () => {
      settled();
    };
  });

  $effect(() => {
    // Завели нового — он должен появиться в списке и быть отмеченным. Связывает
    // человек сам, отдельным нажатием: заведение и привязка — разные решения.
    if (preselect === null) return;
    chosen = preselect;
    // Поиск сбрасываем: заводить новую запись шли как раз потому, что по
    // набранному никого не нашлось, — по нему не найдётся и заведённая, а
    // пропавшую из выдачи отметку `refresh` снимет, и кнопка останется запертой.
    search = '';
    untrack(() => refresh());
  });
</script>

<ModalShell extra="vac-picker-modal" {onclose}>
  {#snippet children()}
    <ModalHead {icon} {title} {onclose} />

    <div class="bar picker-search-bar">
      <SearchBox value={search} {placeholder} onsearch={find} />
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
        {@render rowsMarkup(rows, chosen, pick)}
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

    <ModalFoot
      label={applyLabel}
      busyLabel="Сохраняю…"
      busy={saving}
      {ready}
      oncancel={onclose}
      onconfirm={apply}
    />
  {/snippet}
</ModalShell>

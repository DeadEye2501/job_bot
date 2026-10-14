<script>
  // Поле даты со своей сеткой месяца: день набирают руками или выбирают в
  // календаре.
  //
  // Своим компонентом, а не системным `input[type=date]`: тот рисуется
  // средствами системы, палитры окна не знает и по-русски говорит не везде.
  //
  // Наружу уходит ISO-дата — та, что понимает мост; человеку видно `д.м.г`.
  import { untrack } from 'svelte';

  import { whileOpen } from '$state/outside.js';
  import { WEEKDAYS, monthGrid, monthTitle, shiftMonth } from '$state/calendar.js';
  import { asIso, dayIso, dayOf, isoDay, maskedDate, showDate, validDate } from '$state/dates.js';

  // `disabled` — для даты окончания у места работы, где отмечено «по настоящее
  // время»: набирать там нечего, и календарь не открывается вместе с полем.
  //
  // `up` — раскрыть сетку вверх. Просит тот, под чьим полем места нет; по
  // умолчанию она раскрывается вниз, как её и ищут взглядом.
  //
  // `missing` — обязательная дата пуста, и из-за неё запись не сохранили.
  let { value, onpick, disabled, up, missing } = $props();

  const now = new Date();
  const today = dayIso(now);
  // Календарь открывается на выбранном месяце, а без выбора — на нынешнем.
  const start = untrack(() =>
    value ? dayOf(value) : { year: now.getFullYear(), month: now.getMonth() + 1 },
  );

  // Набранное живёт в поле, а не в отборе: на полпути там обрывок, и уедь он
  // наружу — отбор пошёл бы по недобранной дате.
  let text = $state(untrack(() => showDate(value)));
  // Какое значение поле сейчас показывает. По нему и видно, что дату сменили
  // снаружи: сам набор довода не трогает, пока в поле обрывок.
  let shown = untrack(() => value);
  let year = $state(start.year);
  let month = $state(start.month);
  let open = $state(false);
  let root = $state(null);

  const weeks = $derived(monthGrid(year, month));

  function typed(next) {
    text = next;
    if (next.trim() === '') {
      onpick('');
      return;
    }
    if (validDate(next) !== true) return;
    const iso = asIso(next);
    // Сетка идёт за набранным: иначе набравший «01.03.2026» видит под полем
    // нынешний месяц и не понимает, принято ли набранное.
    const at = dayOf(iso);
    year = at.year;
    month = at.month;
    onpick(iso);
  }

  function pick(day) {
    const iso = isoDay(year, month, day);
    text = showDate(iso);
    open = false;
    onpick(iso);
  }

  function step(by) {
    const at = shiftMonth(year, month, by);
    year = at.year;
    month = at.month;
  }

  $effect(() => {
    // Дату меняют и мимо поля: галочка «по настоящее время» стирает дату
    // окончания у места работы. Не пойди поле за доводом, оно показывало бы
    // стёртое, и человек считал бы, что дата на месте.
    //
    // Набираемое при этом не теряется: недобранная дата наружу не уходит вовсе,
    // и пока в поле обрывок, довод не менялся — а сменился он, значит поле
    // показывает уже не его.
    if (value !== shown) {
      shown = value;
      text = showDate(value);
    }
  });

  $effect(() => {
    // Нажатие мимо закрывает календарь: он накрывает подвал панели отбора, и
    // оставленный открытым прячет «Применить».
    //
    // «Мимо» считается по своему узлу, а не по классу: полей периода два, и
    // нажатие в соседнее по классу читалось бы как нажатие в себя — календарь
    // «от» остался бы висеть над полем «до».
    return whileOpen(open, () => root, () => (open = false));
  });
</script>

<div class="date-picker" bind:this={root}>
  <input
    class="input mono input-date-text"
    class:invalid={validDate(text) === false}
    class:missing
    type="text"
    placeholder="дд.мм.гггг"
    maxlength="10"
    value={text}
    {disabled}
    oninput={(event) => {
      // Поле переписывается и тогда, когда маска не изменила набранного:
      // лишняя девятая цифра осталась бы в поле, хотя в дату не ушла.
      event.currentTarget.value = maskedDate(event.currentTarget.value);
      typed(event.currentTarget.value);
    }}
    onfocus={() => (open = true)}
  />

  {#if open}
    <div class="pop-frame date-panel" class:up>
      <div class="date-head">
        <button class="icon-btn" type="button" title="Прошлый месяц" onclick={() => step(-1)}>
          <span class="material-symbols-outlined">chevron_left</span>
        </button>
        <span class="date-title">{monthTitle(year, month)}</span>
        <button class="icon-btn" type="button" title="Следующий месяц" onclick={() => step(1)}>
          <span class="material-symbols-outlined">chevron_right</span>
        </button>
      </div>

      <div class="date-week">
        {#each WEEKDAYS as name (name)}
          <span class="date-weekday">{name}</span>
        {/each}
      </div>

      {#each weeks as week, at (at)}
        <div class="date-week">
          {#each week as day, cell (cell)}
            {#if day === null}
              <span class="date-cell"></span>
            {:else}
              {@const iso = isoDay(year, month, day)}
              <button
                class="date-cell date-day"
                class:selected={iso === value}
                class:today={iso === today}
                type="button"
                onclick={() => pick(day)}
              >
                {day}
              </button>
            {/if}
          {/each}
        </div>
      {/each}
    </div>
  {/if}
</div>

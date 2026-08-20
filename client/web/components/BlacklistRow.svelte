<script>
  // Строка отсева: род, значение, причина, дата заведения и переключатель.
  //
  // Оба поля правятся на месте и уезжают с задержкой: строку правят по одному
  // знаку — дописывают собачку, чинят опечатку в причине, — и запись на каждый
  // знак послала бы мосту по вопросу на букву.
  import { untrack } from 'svelte';

  import { autosave } from '$state/autosave.js';
  import { shortDate } from '$state/dates.js';
  import { flashing } from '$state/flash.js';

  import RowToggle from './RowToggle.svelte';

  // Пауза перед записью правки. Короче — и мост получает вопрос на каждое
  // слово, длиннее — и человек успевает уйти со строки, не увидев вспышки.
  const EDIT_DELAY = 500;

  let { row, onedit, ontoggle, onremove } = $props();

  let value = $state(untrack(() => row.value));
  let reason = $state(untrack(() => row.reason || ''));
  let valueSaved = $state(false);
  let reasonSaved = $state(false);
  let field = $state(null);

  const markValue = flashing((on) => (valueSaved = on));
  const markReason = flashing((on) => (reasonSaved = on));

  const savers = {
    value: autosave({ delay: EDIT_DELAY, save: (text) => writeValue(text) }),
    reason: autosave({ delay: EDIT_DELAY, save: (text) => writeReason(text) }),
  };

  /** Записать значение.
   *
   * Отклонённое мостом — а пустое значение он отклоняет — в поле не остаётся:
   * человек читал бы своё, а отсев шёл бы по прежнему. Возвращаем то, что
   * осталось в базе: строку к этому времени уже перечитали.
   */
  async function writeValue(text) {
    const done = await onedit({ value: text });
    if (done === null) {
      value = row.value;
      return false;
    }
    markValue();
    return true;
  }

  async function writeReason(text) {
    const done = await onedit({ reason: text });
    if (done === null) {
      reason = row.reason || '';
      return false;
    }
    markReason();
    return true;
  }

  /** Растянуть причину по набранному: она бывает в три строки, а полосы
   *  прокрутки в строке таблицы не разглядеть. */
  function grow() {
    if (field === null) return;
    field.style.height = 'auto';
    field.style.height = `${field.scrollHeight}px`;
  }

  $effect(() => {
    savers.value.known(row.value);
    savers.reason.known(row.reason || '');
  });

  $effect(() => {
    grow();
    return () => {
      // Набранное и не уехавшее отправляем на прощание: строку убрали или
      // отобрали родом, и ждать паузы больше нечему.
      savers.value.flush();
      savers.reason.flush();
    };
  });
</script>

<div class="bl-row" class:disabled={!row.active}>
  <span class="bl-kind-chip {row.kind}">{row.kind}</span>

  <input
    class="inline-edit bl-input value"
    class:saved-flash={valueSaved}
    maxlength="500"
    placeholder="—"
    bind:value
    oninput={() => savers.value.typed(value)}
    onblur={() => savers.value.flush()}
  />

  <textarea
    class="inline-edit bl-input reason"
    class:saved-flash={reasonSaved}
    bind:this={field}
    rows="1"
    maxlength="500"
    placeholder="Причина (опционально)"
    bind:value={reason}
    oninput={() => {
      grow();
      savers.reason.typed(reason);
    }}
    onblur={() => savers.reason.flush()}
  ></textarea>

  <span class="bl-when">{shortDate(row.created_at, new Date())}</span>

  <RowToggle checked={row.active} {ontoggle} />

  <button class="icon-btn" type="button" title="Удалить запись" onclick={() => onremove()}>
    <span class="material-symbols-outlined">delete</span>
  </button>
</div>

<script>
  // Лента жизни вакансии: строка на переход или событие, время справа.
  //
  // Своё пояснение правится прямо в строке: ради одной фразы открывать окно
  // дороже, чем сама правка. Записывается оно с задержкой, как и заметка
  // карточки, и о записи говорит зелёная вспышка рамки.
  //
  // Лента заводится заново на каждую вакансию — этого требует `{#key}` у
  // зовущего: записи, вспышки и набранное помнятся по номеру строки истории, и
  // без пересоздания в них копились бы строки всех вакансий сеанса.
  import { autosave } from '$state/autosave.js';
  import { flashing } from '$state/flash.js';
  import { saveKey } from '$state/keys.js';
  import { ago } from '$state/vacancies.js';

  // Пауза короче, чем у заметки: пояснение — одна фраза, и человек уходит из
  // строки сразу, как её дописал.
  const NOTE_DELAY = 500;

  let { rows, vacancyId, onsave } = $props();

  // Набранное держится здесь: строку перечитывают после каждой записи, и
  // пришедшее из базы иначе стирало бы то, что человек успел дописать.
  let typed = $state({});
  let flashed = $state({});

  // Своя отложенная запись на строку: пауза у каждой считается отдельно, иначе
  // правка второй строки отправляла бы недописанную первую. Своя вспышка — по
  // той же причине: гаснут они порознь.
  const savers = new Map();
  const marks = new Map();

  function saverFor(row) {
    let one = savers.get(row.historyId);
    if (one === undefined) {
      // Номер вакансии запечатан здесь, а не читается на отправке: отложенное
      // уедет к своей строке, даже если человек уже перешёл к соседней
      // вакансии, а вместе с ней сменился и номер в карточке.
      const id = vacancyId;
      one = autosave({ delay: NOTE_DELAY, save: (text) => write(id, row.historyId, text) });
      one.known(row.text);
      savers.set(row.historyId, one);
    }
    return one;
  }

  function markFor(historyId) {
    let one = marks.get(historyId);
    if (one === undefined) {
      one = flashing((on) => (flashed[historyId] = on));
      marks.set(historyId, one);
    }
    return one;
  }

  async function write(id, historyId, text) {
    const done = await onsave(id, historyId, text);
    if (!done) return false;
    markFor(historyId)();
    return true;
  }

  function type(row, field) {
    typed[row.historyId] = field.value;
    grow(field);
    saverFor(row).typed(field.value);
  }

  /** Поле высотой в свой текст: пояснения бывают и в слово, и в абзац, а
   *  прокрутка внутри строки ленты не читается вовсе. */
  function grow(field) {
    field.style.height = 'auto';
    field.style.height = `${field.scrollHeight}px`;
  }

  $effect(() => {
    return () => {
      // Набранное и не уехавшее отправляем на прощание: ленту перерисовывают и
      // на смену статуса, и на весть о разборе.
      savers.forEach((one) => one.flush());
    };
  });
</script>

<div class="timeline">
  {#each rows as row (row.key)}
    <div class="tl-item" class:current={row.current}>
      <span class="status-dot" data-status={row.status}></span>
      <span class="tl-text">
        {#if row.editable}
          <span class="tl-history-row">
            {#if row.label}<span class="tl-label">{row.label}</span>{/if}
            <textarea
              class="inline-edit tl-note"
              class:saved-flash={flashed[row.historyId]}
              rows="1"
              maxlength="2000"
              placeholder="без комментария."
              value={typed[row.historyId] ?? row.text}
              use:grow
              oninput={(event) => type(row, event.currentTarget)}
              onblur={() => saverFor(row).flush()}
              onkeydown={(event) => saveKey(event) && saverFor(row).flush()}
            ></textarea>
          </span>
        {:else}
          {#if row.label}<span class="tl-label">{row.label}</span>{/if}
          <span class="tl-event">{row.text}</span>
        {/if}
      </span>
      <span class="tl-when" title={row.when}>{ago(row.when, new Date())}</span>
    </div>
  {/each}
</div>

<script>
  // Лента жизни вакансии: строка на переход или событие, время справа.
  //
  // Своё пояснение правится прямо в строке: ради одной фразы открывать окно
  // дороже, чем сама правка.
  import { ago } from '$state/vacancies.js';

  let { rows, onsave } = $props();

  // Набранное держится здесь, пока летит запись, и снимается, как только
  // пришёл ответ. Без этого показанное не вернулось бы к тому, что легло:
  // отклонённая правка осталась бы в поле, а дописанная мостом точка не
  // доехала бы — поле уже показывает ту же строку, и менять его нечему.
  let typed = $state({});

  async function save(row, text) {
    typed = { ...typed, [row.historyId]: text };
    await onsave(row.historyId, text);
    const { [row.historyId]: _flown, ...rest } = typed;
    typed = rest;
  }
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
              class="tl-note"
              rows="2"
              maxlength="2000"
              placeholder="без комментария."
              value={typed[row.historyId] ?? row.text}
              onchange={(event) => save(row, event.currentTarget.value)}
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

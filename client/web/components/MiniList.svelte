<script>
  // Короткий список в чужой карточке: коробка, надпись «пусто» и строки,
  // каждая из которых уводит к своей записи.
  //
  // Своим компонентом, потому что люди компании и вакансии карточки устроены
  // одинаково, а нажатие строкой и своя клавиша — то, что в одной из копий
  // легко забыть. Что показать в строке, решает список рода (`MiniPeople`,
  // `MiniVacancies`); раскладка строки у них своя, поэтому и классы свои.
  //
  // `offTip` — почему строка не открывается; пусто — открывается. Выключенная
  // строка не встаёт и в обход клавишей: открыть её нечем.
  import { pressKey } from '$state/keys.js';

  let { items, empty, loading = false, listClass, rowClass, offTip = () => '', onpick, row } = $props();
</script>

<div class="card-section">
  {#if !items.length}
    <div class="mini-list-empty">{empty}</div>
  {:else}
    <div class={listClass}>
      {#each items as one (one.id)}
        {@const off = offTip(one)}
        {#if off}
          <div class="{rowClass} mini-row-off" title={off}>
            {@render row(one)}
          </div>
        {:else}
          <div
            class={rowClass}
            role="button"
            tabindex="0"
            onclick={() => onpick(one.id)}
            onkeydown={(event) => pressKey(event) && onpick(one.id)}
          >
            {@render row(one)}
          </div>
        {/if}
      {/each}
    </div>
    {#if loading}
      <div class="mini-list-more">Загрузка…</div>
    {/if}
  {/if}
</div>

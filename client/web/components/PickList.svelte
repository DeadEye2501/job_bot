<script>
  // Выбор многих из длинного перечня: кнопка со счётом выбранного, под ней
  // поиск и строки с галочками.
  //
  // Не `Dropdown`: там выбирают одно значение из десятка и списка хватает, а
  // здесь выбранных бывает несколько, а самих строк — сотни, и без поиска по
  // ним не попасть.
  //
  // Имена приходят уже просеянными: искать умеет тот, кто знает, что это за
  // имена, а список только показывает переданное.
  let { placeholder, names, chosen, search, onsearch, prefix = '', onpick } = $props();

  let open = $state(false);
</script>

<div class="pick">
  <button class="pick-btn" type="button" onclick={() => (open = !open)}>
    <span>{chosen.size ? `Выбрано: ${chosen.size}` : placeholder}</span>
    <span class="material-symbols-outlined">{open ? 'expand_less' : 'expand_more'}</span>
  </button>
  {#if open}
    <!-- Закрывается по уходу мыши, как и выпадающий список: панель накрывает
         поля под собой, и открытой она мешала бы читать остальную панель. -->
    <div class="pick-panel" role="group" tabindex="-1" onmouseleave={() => (open = false)}>
      <input
        class="input"
        type="text"
        placeholder="Поиск"
        value={search}
        oninput={(event) => onsearch(event.currentTarget.value)}
      />
      <div class="pick-list">
        {#each names as name (name)}
          <label class="checkbox-row">
            <input type="checkbox" checked={chosen.has(name)} onchange={() => onpick(name)} />
            {prefix}{name}
          </label>
        {/each}
        {#if !names.length}<div class="empty-note">Ничего не найдено</div>{/if}
      </div>
    </div>
  {/if}
</div>

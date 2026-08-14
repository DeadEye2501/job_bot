<script>
  // Языки анкеты: строка на язык, уровень выбирается списком.
  import { LANG_LEVELS } from '$state/profile.js';

  import Dropdown from './Dropdown.svelte';

  let { rows, onedit, onadd, onremove } = $props();
</script>

<div class="span-2">
  <div class="lang-list">
    {#each rows as row, index (index)}
      <div class="lang-row">
        <input
          class="input lang-name"
          maxlength="50"
          placeholder="Язык"
          value={row.language}
          onblur={(event) => onedit(index, { language: event.currentTarget.value.trim() })}
        />
        <Dropdown
          options={LANG_LEVELS}
          value={row.level}
          onpick={(level) => onedit(index, { level })}
        />
        <button class="lang-remove" type="button" title="удалить" onclick={() => onremove(index)}>
          ×
        </button>
      </div>
    {/each}
  </div>
  <button class="lang-add" type="button" onclick={() => onadd()}>+ Добавить язык</button>
</div>

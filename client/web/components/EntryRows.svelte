<script>
  // Строки анкеты таблицей: в строке свободный текст и выбор из списка.
  //
  // Так стоят языки (название и уровень) и предпочтения (текст и вид); чем
  // таблицы отличаются, описывает `kind` (`LANGUAGE_ROWS`, `PREFERENCE_ROWS`).
  // Текст пишется как прочие поля анкеты: `ontyped` по ходу набора, `onflush`
  // по уходу из поля и по Ctrl+Enter; выбор — `onpick` сразу.
  import { tick } from 'svelte';

  import { saveKey } from '$state/keys.js';
  import { choiceLabel, choiceValue } from '$state/profile.js';

  import Dropdown from './Dropdown.svelte';

  let { rows, kind, ontyped, onflush, onpick, onadd, onremove } = $props();

  let list = $state(null);

  const labels = $derived(kind.choice.options.map((one) => one.label));

  /** Завести строку и встать в неё курсором.
   *
   * Строку добавляют, чтобы тут же её набрать, — курсор ждать нечему.
   * Ставится он после отрисовки: до неё новой строки в разметке ещё нет.
   */
  async function add() {
    onadd();
    await tick();
    const fields = list.querySelectorAll('.entry-text');
    fields[fields.length - 1].focus();
  }
</script>

<!-- Одной таблицей: строки и «Добавить» под ними в общей рамке. -->
<div class="entry-table {kind.look} span-2" bind:this={list}>
  {#each rows as row, index (index)}
    <div class="entry-row">
      <input
        class="input entry-text"
        maxlength={kind.text.max}
        placeholder={kind.text.placeholder}
        value={row[kind.text.key]}
        oninput={(event) => ontyped(index, { [kind.text.key]: event.currentTarget.value.trim() })}
        onblur={() => onflush()}
        onkeydown={(event) => saveKey(event) && onflush()}
      />
      <Dropdown
        options={labels}
        value={choiceLabel(kind.choice, row[kind.choice.key])}
        onpick={(label) => onpick(index, { [kind.choice.key]: choiceValue(kind.choice, label) })}
      />
      <button class="remove-cross" type="button" title={kind.removeTitle} onclick={() => onremove(index)}>
        ×
      </button>
    </div>
  {/each}
  <button class="add-link entry-add" type="button" onclick={add}>{kind.addLabel}</button>
</div>

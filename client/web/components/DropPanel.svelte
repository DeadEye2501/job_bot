<script>
  // Панель выпадающего списка: имена в столбик, выбранное помечено.
  //
  // Своим компонентом: так падают два списка — выбор из готовых значений и
  // подсказка под полем ввода, — и нарисованы они были дословно одинаково.
  //
  // `keepFocus` — не уводить фокус из поля: подсказка под полем записывает
  // набранное на уходе фокуса, и уйди он на нажатый пункт, выбранное имя
  // уехало бы наверх вторым зовом поверх первого.
  let { options, value, onpick, keepFocus = false } = $props();
</script>

<div class="pop-frame drop-panel cdd-panel" role="listbox" tabindex="-1">
  {#each options as one (one)}
    <button
      class="cdd-option"
      class:active={one === value}
      type="button"
      onmousedown={keepFocus ? (event) => event.preventDefault() : undefined}
      onclick={() => onpick(one)}
    >
      {one}
    </button>
  {/each}
</div>

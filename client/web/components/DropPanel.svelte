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
  <!-- Ключ по месту, а не по значению: имя человека уникальным не бывает, и у
       одного собеседника их трое с одним и тем же. Ключ по значению роняет
       отрисовку на первом же тёзке — панель не появляется вовсе и молча. -->
  {#each options as one, at (at)}
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

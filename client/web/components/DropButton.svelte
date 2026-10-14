<script>
  // Кнопка, открывающая выпадающую панель: подпись и стрелка.
  //
  // Одна на выбор одного значения (`Dropdown`) и выбор многих (`PickList`):
  // открываются они одинаково, и разной кнопкой читались бы как разные
  // элементы. `empty` — подпись-подсказка, пока ничего не выбрано.
  let { label, empty = false, open, ontoggle } = $props();
</script>

<button class="cdd-btn" type="button" onclick={() => ontoggle()}>
  <span class="cdd-label" class:empty>{label}</span>
  <span class="material-symbols-outlined">{open ? 'expand_less' : 'expand_more'}</span>
</button>

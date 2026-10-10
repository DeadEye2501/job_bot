<script>
  // Кнопка заведения записи в полосе над списком контактов: значок в рамке.
  //
  // Своим компонентом, потому что стоит она над каждым списком вкладки, а
  // разметка у неё одна; значок и подсказка — свои у каждого списка.
  let { title, icon = 'add_circle', onclick } = $props();
</script>

<button class="icon-btn cnt-add-btn" type="button" {title} {onclick}>
  <span class="material-symbols-outlined">{icon}</span>
</button>

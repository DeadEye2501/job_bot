<script>
  // Строка поиска над списком.
  let { value, placeholder, onsearch } = $props();
</script>

<label class="search-box">
  <span class="material-symbols-outlined">search</span>
  <input
    class="search-input"
    type="search"
    {value}
    {placeholder}
    oninput={(event) => onsearch(event.currentTarget.value)}
  />
</label>

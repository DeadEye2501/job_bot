<script>
  // Значок «в отсеве» в хвосте строки списка.
  //
  // Своим компонентом: им помечены три списка — люди, компании и каналы, — и
  // значок с подписью были написаны в каждом заново.
  let { blocked } = $props();
</script>

{#if blocked}
  <span class="cnt-hr-bl" title="В blacklist">
    <span class="material-symbols-outlined">block</span>
  </span>
{/if}

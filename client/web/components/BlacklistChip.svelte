<script>
  // Чип «в отсеве» в шапке карточки: значок, слово и само написание отметки в
  // подсказке — по нему видно, чем именно запись отсеяна.
  //
  // Своим компонентом: чип носят три карточки — человека, компании и канала, —
  // и написан он был в каждой заново.
  let { value } = $props();
</script>

{#if value}
  <span class="cnt-det-meta-chip blacklist" title="В blacklist: {value}">
    <span class="material-symbols-outlined">block</span>
    В blacklist
  </span>
{/if}

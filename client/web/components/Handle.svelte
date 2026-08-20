<script>
  // Ник в подписи строки списка — или прямое слово о том, что его нет.
  //
  // Своим компонентом: ник подписывает и человека, и канал, а показанный ник и
  // его отсутствие красятся по-разному. Сами слова приходят готовыми: та же
  // подпись собирается строкой для подборщика, и разойдись они, один человек
  // читался бы в двух местах как двое разных.
  import { handleName } from '$state/telegram.js';

  let { username } = $props();
</script>

{#if username}
  <span class="at">{handleName(username)}</span>
{:else}
  <span class="muted">{handleName(username)}</span>
{/if}

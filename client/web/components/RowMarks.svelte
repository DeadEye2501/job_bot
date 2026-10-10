<script>
  // Хвост строки списка контактов: отметка отсева и счёт вакансий.
  //
  // Своим компонентом, потому что так кончаются строки и компании, и
  // источника. Пустой счёт не рисуется: ноль в пилюле читался бы как «собрали
  // и ничего не нашли».
  import BlacklistMark from './BlacklistMark.svelte';

  let { blocked, count } = $props();
</script>

<BlacklistMark {blocked} />
{#if count > 0}
  <span class="num-pill cnt-co-count">{count}</span>
{/if}

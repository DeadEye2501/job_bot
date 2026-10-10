<script>
  // Строка агрегатора: под именем — где он ищет, значок — сайт или вся сеть.
  import { aggregatorToggle, aggregatorWhere } from '$state/aggregators.js';

  import SourceRow from './SourceRow.svelte';

  let { row, enabled, selected = false, onpick, ontoggle } = $props();
</script>

<SourceRow
  avatar={row.avatar}
  icon={row.is_web_search ? 'travel_explore' : 'language'}
  name={row.name}
  blocked={row.is_blacklisted}
  count={row.vacancy_count}
  toggle={aggregatorToggle(row, enabled)}
  {selected}
  {onpick}
  {ontoggle}
>
  {#snippet sub()}
    {aggregatorWhere(row)}
  {/snippet}
</SourceRow>

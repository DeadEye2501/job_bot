<script>
  // Строка агрегатора: под именем — где он ищет, значок — сайт или вся сеть.
  import { aggregatorToggle, aggregatorWhere } from '$state/aggregators.js';

  import ContactRow from './ContactRow.svelte';

  let { row, enabled, selected = false, onpick, ontoggle } = $props();

  const toggle = $derived(aggregatorToggle(row, enabled));
</script>

<ContactRow
  avatar={row.avatar}
  icon={row.is_web_search ? 'travel_explore' : 'language'}
  name={row.name}
  blocked={row.is_blacklisted}
  dim={toggle.dim}
  count={row.vacancy_count}
  {toggle}
  {selected}
  {onpick}
  {ontoggle}
>
  {#snippet sub()}
    {aggregatorWhere(row)}
  {/snippet}
</ContactRow>

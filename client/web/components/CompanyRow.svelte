<script>
  // Строка компании в списке: значок, имя с подписью, отсев и счёт вакансий.
  import { companyLine, companyTitle } from '$state/companies.js';

  import ContactRow from './ContactRow.svelte';

  let { company, selected = false, onpick } = $props();

  const shown = $derived(companyLine(company));
  const title = $derived(companyTitle(company));
  // Ни сайта, ни алиасов — про это сказано словами, и слова набраны курсивом:
  // так видно, что это не подпись, а её отсутствие.
  const bare = $derived(!company.website && !company.aliases.length);
</script>

<ContactRow
  icon="domain"
  name={title.name}
  named={title.named}
  blocked={company.is_blacklisted}
  dim={company.is_blacklisted}
  count={company.vacancy_count}
  {selected}
  {onpick}
>
  {#snippet sub()}
    {#if bare}<span class="muted">{shown.sub}</span>{:else}{shown.sub}{/if}
  {/snippet}
</ContactRow>

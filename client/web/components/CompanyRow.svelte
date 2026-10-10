<script>
  // Строка компании в списке: значок, имя с подписью, отсев и счёт вакансий.
  import { companyLine, companyTitle } from '$state/companies.js';

  import Avatar from './Avatar.svelte';
  import RowMarks from './RowMarks.svelte';

  let { company, selected = false, onpick } = $props();

  const shown = $derived(companyLine(company));
  const title = $derived(companyTitle(company));
  // Ни сайта, ни алиасов — про это сказано словами, и слова набраны курсивом:
  // так видно, что это не подпись, а её отсутствие.
  const bare = $derived(!company.website && !company.aliases.length);
</script>

<button
  class="cnt-hr-row"
  class:selected
  class:blacklisted={company.is_blacklisted}
  type="button"
  onclick={() => onpick()}
>
  <Avatar icon="domain" />

  <span class="cnt-hr-info">
    <span class="cnt-hr-name" class:muted={!title.named}>
      {title.name}
    </span>
    <span class="cnt-hr-sub">
      {#if bare}<span class="muted">{shown.sub}</span>{:else}{shown.sub}{/if}
    </span>
  </span>

  <span class="cnt-hr-trailing">
    <RowMarks blocked={company.is_blacklisted} count={company.vacancy_count} />
  </span>
</button>

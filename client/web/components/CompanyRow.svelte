<script>
  // Строка компании в списке: значок, имя с подписью, отсев и счёт вакансий.
  import { companyLine } from '$state/companies.js';

  import Avatar from './Avatar.svelte';

  let { company, selected = false, onpick } = $props();

  const shown = $derived(companyLine(company));
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
    <span class="cnt-hr-name" class:muted={!company.name}>
      {company.name || '— без названия —'}
    </span>
    <span class="cnt-hr-sub">
      {#if bare}<span class="muted">{shown.sub}</span>{:else}{shown.sub}{/if}
    </span>
  </span>

  <span class="cnt-hr-trailing">
    {#if company.is_blacklisted}
      <span class="cnt-hr-bl" title="В blacklist">
        <span class="material-symbols-outlined">block</span>
      </span>
    {/if}
    {#if company.vacancy_count > 0}
      <span class="cnt-co-count">{company.vacancy_count}</span>
    {/if}
  </span>
</button>

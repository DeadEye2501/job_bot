<script>
  // Строка компании: значок, имя с подписью и счёт её вакансий.
  import { companyLine } from '$state/companies.js';

  let { company, onpick } = $props();

  const shown = $derived(companyLine(company));
</script>

<div class="contact-row" class:blocked={company.is_blacklisted}>
  <button class="contact-main" type="button" onclick={() => onpick()}>
    <span class="avatar avatar-empty material-symbols-outlined">domain</span>
    <span class="contact-names">
      <span class="contact-name">{shown.name}</span>
      <span class="contact-handle">{shown.sub}</span>
    </span>
    <!-- У компании нет переключателя, поэтому отсев назван словом: приглушённой
         строкой одной он читался бы как «просто пустая». -->
    {#if company.is_blacklisted}
      <span class="kind-tag" data-kind="company">в отсеве</span>
    {/if}
    <span class="contact-count">{company.vacancy_count}</span>
  </button>
</div>

<script>
  // Строка человека: снимок, имя с подписью и счёт непрочитанного.
  import { personLine } from '$state/contacts.js';

  import UnreadBadge from './UnreadBadge.svelte';

  let { person, onpick } = $props();

  const shown = $derived(personLine(person));
</script>

<div class="contact-row" class:blocked={person.is_blacklisted}>
  <button class="contact-main" type="button" onclick={() => onpick()}>
    {#if person.avatar}
      <img class="avatar" src={person.avatar} alt="" />
    {:else}
      <span class="avatar avatar-empty material-symbols-outlined">person</span>
    {/if}
    <span class="contact-names">
      <span class="contact-name">{shown.name}</span>
      <span class="contact-handle">{shown.sub}</span>
    </span>
    <!-- У человека нет переключателя, поэтому отсев назван словом: приглушённой
         строкой одной он читался бы как «просто пустая». -->
    {#if person.is_blacklisted}
      <span class="kind-tag" data-kind="hr">в отсеве</span>
    {/if}
    {#if person.unread_count}
      <UnreadBadge count={person.unread_count} />
    {/if}
    <span class="contact-count">{person.vacancy_count}</span>
  </button>
</div>

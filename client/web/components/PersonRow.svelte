<script>
  // Строка человека в списке: снимок, имя с подписью, отсев и непрочитанное.
  import { personName } from '$state/contacts.js';

  import Avatar from './Avatar.svelte';

  let { person, selected = false, onpick } = $props();

  const named = $derived(Boolean(person.name || person.telegram_username));
</script>

<button
  class="cnt-hr-row"
  class:selected
  class:blacklisted={person.is_blacklisted}
  type="button"
  onclick={() => onpick()}
>
  <Avatar avatar={person.avatar} name={person.name} icon="person" />

  <span class="cnt-hr-info">
    <span class="cnt-hr-name" class:muted={!named}>
      {named ? personName(person) : '— без имени —'}
    </span>
    <!-- Ник и компания — то, чем различают тёзок: по нику находят в Telegram,
         по компании вспоминают, откуда человек писал. Обе половины названы
         всегда: пустое место читалось бы как недогрузившаяся строка. -->
    <span class="cnt-hr-sub">
      {#if person.telegram_username}
        <span class="at">@{person.telegram_username}</span>
      {:else}
        <span class="muted">без @username</span>
      {/if}
      <span class="sep">·</span>
      {#if person.last_company_name}
        <span class="company">{person.last_company_name}</span>
      {:else}
        <span class="muted">без компании</span>
      {/if}
    </span>
  </span>

  <span class="cnt-hr-trailing">
    {#if person.is_blacklisted}
      <span class="cnt-hr-bl" title="В blacklist">
        <span class="material-symbols-outlined">block</span>
      </span>
    {/if}
    {#if person.unread_count}
      <span class="cnt-hr-unread">{person.unread_count}</span>
    {/if}
  </span>
</button>

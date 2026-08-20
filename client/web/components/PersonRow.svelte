<script>
  // Строка человека в списке: снимок, имя с подписью, отсев и непрочитанное.
  import { personSub, personTitle } from '$state/people.js';

  import Avatar from './Avatar.svelte';
  import BlacklistMark from './BlacklistMark.svelte';
  import Handle from './Handle.svelte';

  let { person, selected = false, onpick } = $props();

  const shown = $derived(personTitle(person));
  const sub = $derived(personSub(person));
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
    <span class="cnt-hr-name" class:muted={!shown.named}>
      {shown.name}
    </span>
    <!-- Ник и компания красятся порознь: по нику находят в Telegram, по
         компании вспоминают, откуда человек писал. -->
    <span class="cnt-hr-sub">
      <Handle username={person.telegram_username} />
      <span class="sep">·</span>
      {#if person.last_company_name}
        <span class="company">{sub.company}</span>
      {:else}
        <span class="muted">{sub.company}</span>
      {/if}
    </span>
  </span>

  <span class="cnt-hr-trailing">
    <BlacklistMark blocked={person.is_blacklisted} />
    {#if person.unread_count}
      <span class="cnt-hr-unread">{person.unread_count}</span>
    {/if}
  </span>
</button>

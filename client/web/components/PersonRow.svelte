<script>
  // Строка человека в списке: снимок, имя с подписью, отсев и непрочитанное.
  import { personSub, personTitle } from '$state/people.js';

  import ContactRow from './ContactRow.svelte';
  import Handle from './Handle.svelte';

  let { person, selected = false, onpick } = $props();

  const shown = $derived(personTitle(person));
  const line = $derived(personSub(person));
</script>

<ContactRow
  avatar={person.avatar}
  initialsOf={person.name}
  icon="person"
  name={shown.name}
  named={shown.named}
  blocked={person.is_blacklisted}
  dim={person.is_blacklisted}
  unread={person.unread_count}
  {selected}
  {onpick}
>
  <!-- Ник и компания красятся порознь: по нику находят в Telegram, по
       компании вспоминают, откуда человек писал. -->
  {#snippet sub()}
    <Handle username={person.telegram_username} />
    <span class="sep">·</span>
    {#if person.last_company_name}
      <span class="company">{line.company}</span>
    {:else}
      <span class="muted">{line.company}</span>
    {/if}
  {/snippet}
</ContactRow>

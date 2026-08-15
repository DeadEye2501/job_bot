<script>
  // Строка канала: значок, имя с ником, отсев, счёт вакансий и переключатель.
  import { channelToggle } from '$state/contacts.js';

  import Avatar from './Avatar.svelte';

  let { channel, selected = false, onpick, ontoggle } = $props();

  const shown = $derived(channelToggle(channel));
</script>

<div class="cnt-hr-row" class:selected class:blacklisted={shown.dim}>
  <Avatar avatar={channel.avatar} icon="tag" />

  <button class="cnt-hr-info" type="button" onclick={() => onpick()}>
    <span class="cnt-hr-name" class:muted={!channel.title && !channel.username}>
      {channel.title || (channel.username ? `@${channel.username}` : '— без названия —')}
    </span>
    <span class="cnt-hr-sub">
      {#if channel.username}
        <span class="at">@{channel.username}</span>
      {:else}
        <span class="muted">без @username</span>
      {/if}
    </span>
  </button>

  <span class="cnt-hr-trailing">
    {#if channel.is_blacklisted}
      <span class="cnt-hr-bl" title="В blacklist">
        <span class="material-symbols-outlined">block</span>
      </span>
    {/if}
    {#if channel.vacancy_count > 0}
      <span class="cnt-co-count">{channel.vacancy_count}</span>
    {/if}
    <!-- Канал из отсева включить нельзя: обход всё равно его пропустит, и
         включённый переключатель обещал бы работу, которой не будет. -->
    <input
      type="checkbox"
      class="toggle compact"
      class:locked={shown.disabled}
      checked={shown.checked}
      disabled={shown.disabled}
      title={shown.title}
      onchange={(event) => ontoggle(event.currentTarget.checked)}
    />
  </span>
</div>

<script>
  // Строка канала: значок, имя с ником, отсев, счёт вакансий и переключатель.
  import { channelToggle } from '$state/channels.js';

  import Avatar from './Avatar.svelte';
  import BlacklistMark from './BlacklistMark.svelte';
  import Handle from './Handle.svelte';
  import RowToggle from './RowToggle.svelte';

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
      <Handle username={channel.username} />
    </span>
  </button>

  <span class="cnt-hr-trailing">
    <BlacklistMark blocked={channel.is_blacklisted} />
    {#if channel.vacancy_count > 0}
      <span class="cnt-co-count">{channel.vacancy_count}</span>
    {/if}
    <!-- Канал из отсева включить нельзя: обход всё равно его пропустит, и
         включённый переключатель обещал бы работу, которой не будет. -->
    <RowToggle
      checked={shown.checked}
      disabled={shown.disabled}
      title={shown.title}
      {ontoggle}
    />
  </span>
</div>

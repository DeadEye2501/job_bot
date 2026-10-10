<script>
  // Строка канала: под названием — ник, значок — решётка.
  import { channelTitle, channelToggle } from '$state/channels.js';

  import ContactRow from './ContactRow.svelte';
  import Handle from './Handle.svelte';

  let { channel, enabled, selected = false, onpick, ontoggle } = $props();

  const title = $derived(channelTitle(channel));
  const toggle = $derived(channelToggle(channel, enabled));
</script>

<ContactRow
  avatar={channel.avatar}
  icon="tag"
  name={title.name}
  named={title.named}
  blocked={channel.is_blacklisted}
  dim={toggle.dim}
  count={channel.vacancy_count}
  {toggle}
  {selected}
  {onpick}
  {ontoggle}
>
  {#snippet sub()}
    <Handle username={channel.username} />
  {/snippet}
</ContactRow>

<script>
  // Строка канала: под названием — ник, значок — решётка.
  import { channelTitle, channelToggle } from '$state/channels.js';

  import Handle from './Handle.svelte';
  import SourceRow from './SourceRow.svelte';

  let { channel, enabled, selected = false, onpick, ontoggle } = $props();

  const title = $derived(channelTitle(channel));
</script>

<SourceRow
  avatar={channel.avatar}
  icon="tag"
  name={title.name}
  named={title.named}
  blocked={channel.is_blacklisted}
  count={channel.vacancy_count}
  toggle={channelToggle(channel, enabled)}
  {selected}
  {onpick}
  {ontoggle}
>
  {#snippet sub()}
    <Handle username={channel.username} />
  {/snippet}
</SourceRow>

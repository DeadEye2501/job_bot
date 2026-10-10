<script>
  // Вкладка «Каналы»: общая вкладка источников со строкой и карточкой канала.

  import { call } from '$api/bridge.js';
  import ChannelRow from '$components/ChannelRow.svelte';
  import { CHANNELS_TAB } from '$state/channels.js';

  import ChannelCard from './ChannelCard.svelte';
  import SourcesTab from './SourcesTab.svelte';

  let { ask, say, lockedTip, events, open, onopened, onvacancy } = $props();

  const source = {
    key: 'channels',
    read: (search) => ask('channels.list', { search }),
    setActive: (channel, on) => ask('channels.set_active', { channel_id: channel.id, is_active: on }),
    setAll: (on) => ask('channels.set_all_active', { is_active: on }),
    save: (draft) => call('channels.create', { input: draft.trim() }),
  };
</script>

<SourcesTab kind="channel" words={CHANNELS_TAB} {source} {say} {events} {open} {onopened}>
  {#snippet row(channel, at)}
    <ChannelRow
      {channel}
      enabled={at.enabled}
      selected={at.selected}
      onpick={at.pick}
      ontoggle={at.toggle}
    />
  {/snippet}

  {#snippet pane(shown)}
    <ChannelCard
      bind:this={shown.getCard, shown.setCard}
      {ask}
      {say}
      {lockedTip}
      {events}
      {onvacancy}
      channelId={shown.opened}
      onclose={shown.close}
      onchanged={shown.list.again}
    />
  {/snippet}
</SourcesTab>

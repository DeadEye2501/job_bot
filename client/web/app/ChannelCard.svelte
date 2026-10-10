<script>
  // Карточка канала: его числа, воронка и вакансии, которые он принёс.
  //
  // Стоит правой панелью рядом со списком: канал правят, глядя на его же числа,
  // и уводить ради этого с экрана значило бы терять из виду соседей по списку.

  import ActionsMenu from '$components/ActionsMenu.svelte';
  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import BlacklistMenuItem from '$components/BlacklistMenuItem.svelte';
  import CardHandle from '$components/CardHandle.svelte';
  import CardPane from '$components/CardPane.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MenuItem from '$components/MenuItem.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import SourceStats from '$components/SourceStats.svelte';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { channelName, pollBlock } from '$state/channels.js';
  import { round } from '$state/round.svelte.js';
  import { sourceCard } from '$state/source_card.svelte.js';

  let { ask, say, lockedTip, events, channelId, onvacancy, onclose, onchanged } = $props();

  let asking = $state(false);

  // Каналов с тысячей вакансий хватает, и разом такой список не рисуется.
  const source = sourceCard({
    ask: (...args) => ask(...args),
    method: 'channels.detail',
    trouble: 'Не удалось прочитать канал',
    vacanciesOf: (id) => (page) => ask('channels.vacancies', { channel_id: id, ...page }),
  });
  const card = $derived(source.card);

  const dropCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'channels.delete',
    note: 'Канал удалён',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
  });

  const blocking = cardBlocking({
    ask: (...args) => ask(...args),
    block: 'channels.block',
    unblock: 'channels.unblock',
    say: (text) => say(text),
    reread: () => source.read(channelId),
    onchanged: () => onchanged(),
  });

  const shown = $derived(card ? channelName({ ...card, id: card.channel_id }) : null);
  const pollTip = $derived(pollBlock(card, lockedTip, round.running));

  /** Дочитать следующую страницу вакансий: панель подошла к концу.
   *
   * Зовёт список — прокручивается панель целиком, вместе с шапкой и числами, и
   * знает об этой прокрутке она.
   */
  export function more() {
    source.more(channelId);
  }

  /** Опросить канал сейчас.
   *
   * Просьба уходит боту, а он при погасших лампах не поднят вовсе: пункт заперт
   * и объяснён теми же словами, что и кнопка обхода внизу окна.
   *
   * Ответа о прогоне здесь не ждут: на каждый новый пост уходит до пяти
   * обращений к модели. Чем кончилось, скажет оболочка вестью об исходе, а
   * числа карточки подтянутся вестью о смене списка вакансий.
   */
  async function pollNow() {
    const done = await ask('channels.poll_now', channelId);
    if (done === null) return;
    say('Прогон канала запущен');
  }

  async function resetCursor() {
    const done = await ask('channels.reset_cursor', channelId);
    if (done === null) return;
    say(
      'Отметка прочитанного сброшена — следующий обход перечитает последние посты канала ' +
        '(сколько именно, задаёт глубина добора)',
    );
  }

  async function drop() {
    asking = false;
    await dropCard(channelId);
  }

  $effect(() => source.watch(events, channelId));
</script>

<CardPane trouble={source.trouble} ready={!!card}>
  <div class="cnt-det-head">
    <Avatar avatar={card.avatar} icon="tag" />

    <div>
      <div class="cnt-det-name">{shown.name}</div>

      <div class="cnt-det-sub">
        <CardHandle username={card.username} onopen={(url) => ask('system.open_url', url)} />
      </div>

      <div class="cnt-det-meta-row">
        <BlacklistChip value={card.blacklist_value} />
      </div>
    </div>

    <ActionsMenu>
      {#snippet children(close)}
        <MenuItem
          icon="refresh"
          label="Прогнать сейчас"
          title={pollTip || 'Запустить поллинг этого канала'}
          disabled={!!pollTip}
          {close}
          onpick={pollNow}
        />
        <MenuItem
          icon="restart_alt"
          label="Сбросить курсор"
          title="Сбросить last_processed_msg_id"
          {close}
          onpick={resetCursor}
        />
        <BlacklistMenuItem
          blocked={!!card.blacklist_value}
          {close}
          onblock={() => blocking.block(channelId)}
          onunblock={() => blocking.unblock(channelId)}
        />

        <div class="menu-line"></div>

        <MenuItem
          icon="delete"
          label="Удалить канал"
          danger
          {close}
          onpick={() => (asking = true)}
        />
      {/snippet}
    </ActionsMenu>
  </div>

  <SourceStats stats={card.stats} empty="Из этого канала ещё не пришло вакансий" />

  <MiniVacancies
    vacancies={source.vacancies.rows}
    empty="Из этого канала ещё нет вакансий."
    loading={source.vacancies.digging}
    onpick={onvacancy}
  />
</CardPane>

{#if asking}
  <ConfirmDialog
    message={`Удалить «${shown.name}»?\n\nСвязанные вакансии останутся, но без привязки к каналу. Действие необратимо.`}
    confirmLabel="Удалить"
    onconfirm={drop}
    oncancel={() => (asking = false)}
  />
{/if}

<script>
  // Карточка канала: его числа, воронка и вакансии, которые он принёс.
  //
  // Стоит правой панелью рядом со списком: канал правят, глядя на его же числа,
  // и уводить ради этого с экрана значило бы терять из виду соседей по списку.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import CardActions from '$components/CardActions.svelte';
  import CardHandle from '$components/CardHandle.svelte';
  import CardPane from '$components/CardPane.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MenuItem from '$components/MenuItem.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import SourceStats from '$components/SourceStats.svelte';
  import { cardActions } from '$state/card_actions.svelte.js';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { channelName, pollBlock } from '$state/channels.js';
  import { round } from '$state/round.svelte.js';
  import { sourceCard } from '$state/source_card.svelte.js';

  let { ask, say, lockedTip, events, channelId, onvacancy, onclose, onchanged } = $props();

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

  // Слияния у канала нет: из общих действий карточки ему нужно одно удаление.
  const acts = cardActions({ id: () => channelId, dropCard, mergeCard: null });

  const blocking = cardBlocking({
    block: (id) => ask('channels.block', id),
    unblock: (id) => ask('channels.unblock', id),
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

    {#snippet lead(close)}
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
    {/snippet}
    <CardActions
      {lead}
      blocked={!!card.blacklist_value}
      deleteLabel="Удалить канал"
      onblock={() => blocking.block(channelId)}
      onunblock={() => blocking.unblock(channelId)}
      ondelete={() => (acts.asking = 'delete')}
    />
  </div>

  <SourceStats stats={card.stats} empty="Из этого канала ещё не пришло вакансий" />

  <MiniVacancies
    vacancies={source.vacancies.rows}
    empty="Из этого канала ещё нет вакансий."
    loading={source.vacancies.digging}
    onpick={onvacancy}
  />
</CardPane>

{#if acts.asking === 'delete'}
  <ConfirmDialog
    message={`Удалить «${shown.name}»?\n\nСвязанные вакансии останутся, но без привязки к каналу. Действие необратимо.`}
    confirmLabel="Удалить"
    onconfirm={() => acts.drop()}
    oncancel={() => (acts.asking = null)}
  />
{/if}

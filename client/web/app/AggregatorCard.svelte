<script>
  // Карточка агрегатора: его числа, воронка и вакансии, которые он принёс.
  //
  // Устроена как карточка канала: это тоже источник, и смотрят на него так же.
  // Своё у агрегатора — вход на сайт и запоры агента: без входа и без
  // водителя с браузером обходить его нечем.

  import ActionsMenu from '$components/ActionsMenu.svelte';
  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import BlacklistMenuItem from '$components/BlacklistMenuItem.svelte';
  import CardPane from '$components/CardPane.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import MenuItem from '$components/MenuItem.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import SourceStats from '$components/SourceStats.svelte';
  import { LOGIN_FIRST, actionBlock, aggregatorLastRun, aggregatorWhere } from '$state/aggregators.js';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { RUNNING, round } from '$state/round.svelte.js';
  import { siteHref } from '$state/site.js';
  import { sourceCard } from '$state/source_card.svelte.js';

  let { ask, say, lockedTip, lock, events, aggregatorId, onvacancy, onclose, onchanged } = $props();

  // Сколько откликов уйдёт без привязки, если удаление подтвердят; пусто — не
  // спрашиваем.
  let asking = $state(null);

  const source = sourceCard({
    ask: (...args) => ask(...args),
    method: 'aggregators.detail',
    trouble: 'Не удалось прочитать агрегатор',
    vacanciesOf: (id) => (page) => ask('aggregators.vacancies', { aggregator_id: id, ...page }),
  });
  const card = $derived(source.card);

  // С откликами мост сперва спрашивает — их число и называется в
  // подтверждении; без откликов удаляет сразу.
  const dropCard = cardFinish({
    ask: (...args) => ask(...args),
    method: 'aggregators.delete',
    note: 'Агрегатор удалён',
    say: (text) => say(text),
    onchanged: () => onchanged(),
    onclose: () => onclose(),
    held: (done) => {
      asking = done.confirm ?? null;
      return asking !== null;
    },
  });

  const blocking = cardBlocking({
    ask: (...args) => ask(...args),
    block: 'aggregators.block',
    unblock: 'aggregators.unblock',
    say: (text) => say(text),
    reread: () => source.read(aggregatorId),
    onchanged: () => onchanged(),
  });

  const block = $derived(
    actionBlock({ blocked: !!card?.blacklist_value, running: round.running, lock, lockedTip }),
  );
  const runTip = $derived(block || (card && !card.is_logged_in ? LOGIN_FIRST : ''));

  /** Дочитать следующую страницу: зовёт список — прокручивается панель целиком. */
  export function more() {
    source.more(aggregatorId);
  }

  /** Войти на сайт: мост открывает видимый браузер, чем кончилось — скажет весть. */
  async function login() {
    const done = await ask('aggregators.login', aggregatorId);
    if (done !== null) say(`Войдите на ${card.host} в открывшемся окне и закройте его`);
  }

  async function runNow() {
    const done = await ask('aggregators.run_now', aggregatorId);
    if (done !== null) say('Обход источника запущен');
  }

  function drop() {
    return dropCard({ aggregator_id: aggregatorId, confirmed: false });
  }

  async function dropConfirmed() {
    asking = null;
    await dropCard({ aggregator_id: aggregatorId, confirmed: true });
  }

  // Вход и обход кончаются вестью о конце прогона: отметка входа и время
  // обхода в шапке меняются тогда.
  $effect(() => round.onFinish(() => source.read(aggregatorId)));

  $effect(() => source.watch(events, aggregatorId));
</script>

<CardPane trouble={source.trouble} ready={!!card}>
  <div class="cnt-det-head">
    <Avatar avatar={card.avatar} icon={card.is_web_search ? 'travel_explore' : 'language'} />

    <div>
      <div class="login-line">
        <div class="cnt-det-name">{card.name}</div>
        {#if !card.is_web_search}
          <!-- Вход — значком рядом с именем: он же и показывает, выполнен ли
               вход, и по нажатию открывает сайт войти (заново). -->
          <button
            class="icon-btn login-mark"
            class:done={card.is_logged_in}
            type="button"
            title={block || (card.is_logged_in ? 'Вход выполнен — нажмите, чтобы войти заново' : 'Войти на сайт')}
            disabled={!!block}
            onclick={login}
          >
            <span class="material-symbols-outlined">{card.is_logged_in ? 'how_to_reg' : 'login'}</span>
          </button>
        {/if}
      </div>

      <div class="cnt-det-sub">
        {#if card.is_web_search}
          <span>{aggregatorWhere(card)}</span>
        {:else}
          <button
            class="cnt-det-link"
            type="button"
            title="Открыть сайт"
            onclick={() => ask('system.open_url', siteHref(card.host))}
          >
            {card.host}
          </button>
        {/if}
      </div>

      <div class="cnt-det-meta-row">
        <span class="cnt-det-meta-chip">{aggregatorLastRun(card)}</span>
        <BlacklistChip value={card.blacklist_value} />
      </div>
    </div>

    <ActionsMenu>
      {#snippet children(close)}
        <MenuItem
          icon="refresh"
          label="Прогнать сейчас"
          title={runTip || 'Обойти этот источник сейчас'}
          disabled={!!runTip}
          {close}
          onpick={runNow}
        />
        {#if !card.is_web_search}
          <BlacklistMenuItem
            blocked={!!card.blacklist_value}
            {close}
            onblock={() => blocking.block(aggregatorId)}
            onunblock={() => blocking.unblock(aggregatorId)}
          />

          <div class="menu-line"></div>

          <MenuItem
            icon="delete"
            label="Удалить агрегатор"
            danger
            title={round.running ? RUNNING : null}
            disabled={round.running}
            {close}
            onpick={drop}
          />
        {/if}
      {/snippet}
    </ActionsMenu>
  </div>

  <SourceStats stats={card.stats} empty="С этого агрегатора ещё не пришло вакансий" />

  <MiniVacancies
    vacancies={source.vacancies.rows}
    empty="С этого агрегатора ещё нет вакансий."
    loading={source.vacancies.digging}
    onpick={onvacancy}
  />
</CardPane>

{#if asking !== null}
  <ConfirmDialog
    message={`Удалить «${card.name}»?\n\nОткликов на его вакансии: ${asking}. Вакансии и отклики останутся, но без привязки к агрегатору; вход на сайт придётся пройти заново. Действие необратимо.`}
    confirmLabel="Удалить"
    onconfirm={dropConfirmed}
    oncancel={() => (asking = null)}
  />
{/if}

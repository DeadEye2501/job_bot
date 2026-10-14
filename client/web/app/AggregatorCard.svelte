<script>
  // Карточка агрегатора: его числа, воронка и вакансии, которые он принёс.
  //
  // Устроена как карточка канала: это тоже источник, и смотрят на него так же.
  // Своё у агрегатора — вход на сайт и запоры агента: без входа и без
  // водителя с браузером обходить его нечем.

  import Avatar from '$components/Avatar.svelte';
  import BlacklistChip from '$components/BlacklistChip.svelte';
  import CardActions from '$components/CardActions.svelte';
  import CardPane from '$components/CardPane.svelte';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import LoginMark from '$components/LoginMark.svelte';
  import MenuItem from '$components/MenuItem.svelte';
  import MiniVacancies from '$components/MiniVacancies.svelte';
  import ResumeList from '$components/ResumeList.svelte';
  import SourceStats from '$components/SourceStats.svelte';
  import {
    actionBlock,
    aggregatorWhere,
    loginMark,
    newResumeTip,
    siteTip,
  } from '$state/aggregators.js';
  import { cardBlocking } from '$state/card_block.js';
  import { cardFinish } from '$state/card_finish.js';
  import { RUNNING } from '$state/progress.js';
  import { round } from '$state/round.svelte.js';
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
    block: (id) => ask('aggregators.block', id),
    unblock: (id) => ask('aggregators.unblock', id),
    say: (text) => say(text),
    reread: () => source.read(aggregatorId),
    onchanged: () => onchanged(),
  });

  const block = $derived(
    actionBlock({ blocked: !!card?.blacklist_value, running: round.running, lock, lockedTip }),
  );
  const runTip = $derived(card ? siteTip(card, block) : '');
  const createTip = $derived(card ? newResumeTip(card, block) : '');
  const dropTip = $derived(round.running ? RUNNING : '');

  /** Дочитать следующую страницу: зовёт список — прокручивается панель целиком. */
  export function more() {
    source.more(aggregatorId);
  }

  /** Пустить работу агента на сайте: мост отвечает «пущено» — сказать, что
   *  пошло; чем кончилось, скажет весть. */
  async function launch(method, payload, started) {
    const done = await ask(method, payload);
    if (done !== null) say(started);
  }

  /** Войти на сайт: мост открывает видимый браузер. */
  const login = () =>
    launch('aggregators.login', aggregatorId, `Войдите на ${card.host} в открывшемся окне и закройте его`);
  const runNow = () => launch('aggregators.run_now', aggregatorId, 'Обход источника запущен');
  const scan = () => launch('aggregators.scan', aggregatorId, 'Резюме обновляются');
  const fillResume = (resumeId) =>
    launch('aggregators.fill_resume', { aggregator_id: aggregatorId, resume_id: resumeId }, 'Резюме заполняется');
  const createResume = () => launch('aggregators.create_resume', aggregatorId, 'Новое резюме заполняется');

  async function chooseResume(resumeId) {
    await ask('aggregators.choose_resume', { aggregator_id: aggregatorId, resume_id: resumeId });
    source.read(aggregatorId);
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
          <LoginMark
            mark={loginMark(card.is_logged_in, block)}
            disabled={!!block}
            onlogin={login}
          />
        {/if}
      </div>

      <div class="cnt-det-sub">
        {#if card.is_web_search}
          <span>{aggregatorWhere(card)}</span>
        {:else}
          <button
            class="cnt-det-link link-hover"
            type="button"
            title="Открыть сайт"
            onclick={() => ask('system.open_url', siteHref(card.host))}
          >
            {card.host}
          </button>
        {/if}
      </div>

      <div class="cnt-det-meta-row">
        <BlacklistChip value={card.blacklist_value} />
      </div>
    </div>

    {#snippet lead(close)}
      {#if !card.is_web_search}
        <MenuItem
          icon="add_circle"
          label="Создать новое резюме"
          title={createTip || 'Завести на сайте новое резюме по вашей анкете'}
          disabled={!!createTip}
          {close}
          onpick={createResume}
        />
        <MenuItem
          icon="sync"
          label="Обновить список резюме"
          title={runTip || 'Перечислить ваши резюме на сайте заново'}
          disabled={!!runTip}
          {close}
          onpick={scan}
        />

        <div class="menu-line"></div>
      {/if}
      <MenuItem
        icon="refresh"
        label="Прогнать сейчас"
        title={runTip || 'Обойти этот источник сейчас'}
        disabled={!!runTip}
        {close}
        onpick={runNow}
      />
    {/snippet}
    <CardActions
      {lead}
      blocked={!!card.blacklist_value}
      deleteLabel="Удалить агрегатор"
      deleteTip={dropTip}
      removable={!card.is_web_search}
      onblock={() => blocking.block(aggregatorId)}
      onunblock={() => blocking.unblock(aggregatorId)}
      ondelete={drop}
    />
  </div>

  {#if !card.is_web_search}
    <ResumeList
      resumes={card.resumes}
      site={card.name}
      rewriteTip={block}
      onchoose={chooseResume}
      onrewrite={fillResume}
      onopen={(url) => ask('system.open_url', url)}
    />
  {/if}

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
    locked={dropTip}
    onconfirm={dropConfirmed}
    oncancel={() => (asking = null)}
  />
{/if}

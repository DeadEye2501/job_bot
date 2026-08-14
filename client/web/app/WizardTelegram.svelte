<script>
  // Шаг мастера: учётная запись Telegram.
  //
  // Тот же раздел, что и в настройках, и тот же вход в три шага: заводить для
  // мастера второй значило бы держать два входа в один Telegram.
  import TelegramSection from '$components/TelegramSection.svelte';
  import WizardFoot from '$components/WizardFoot.svelte';

  import { loginTrouble } from '$state/settings.js';

  import TelegramLogin from './TelegramLogin.svelte';

  let { ask, say, onback, onnext } = $props();

  const NEED_SESSION = 'Войдите в Telegram, чтобы идти дальше';

  let tg = $state(null);
  let draft = $state({ api_id: '', api_hash: '', phone: '' });
  let logging = $state(false);

  let alive = true;

  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive) return;
    tg = now.tg;
    if (!draft.api_id) draft = { api_id: tg.api_id, api_hash: tg.api_hash, phone: tg.phone };
  }

  function startLogin() {
    const trouble = loginTrouble(draft);
    if (trouble) return say(trouble, true);
    logging = true;
  }

  /** Выйти из сеанса.
   *
   * Кнопка та же, что и в настройках, и делает то же самое: человек, вошедший
   * не тем номером, чинит это здесь, не доходя до конца мастера.
   */
  async function logout() {
    const done = await ask('settings.logout');
    if (done === null) return;
    return refresh();
  }

  /** Уйти дальше. Заслон назван словом, а не запертой кнопкой: запертая
   *  оставляет человека гадать, чего ей не хватило. */
  function ahead() {
    if (!tg?.has_session) return say(NEED_SESSION, true);
    return onnext();
  }

  function loggedIn() {
    logging = false;
    say('Вход выполнен');
    return refresh();
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

<div class="wiz-body">
  <div class="wiz-title">Учётная запись Telegram</div>
  <p class="wiz-text">
    Бот читает каналы и пишет людям от вашего имени. Заведите для него отдельную
    учётную запись: за рассылку незнакомым людям Telegram блокирует номер, и
    терять на этом основной не стоит.
  </p>
  <p class="wiz-text">
    <strong>api_id</strong> и <strong>api_hash</strong> берутся на my.telegram.org — раздел
    «API development tools». Ключи остаются на этом компьютере.
  </p>

  {#if tg}
    <TelegramSection
      {tg}
      {draft}
      onedit={(part) => (draft = { ...draft, ...part })}
      onlogin={startLogin}
      onlogout={logout}
    />
  {/if}
</div>

<WizardFoot
  trouble={tg?.has_session ? '' : NEED_SESSION}
  nextLabel="Дальше"
  busy={!tg}
  {onback}
  onnext={ahead}
/>

{#if logging}
  <TelegramLogin creds={draft} ondone={loggedIn} onclose={() => (logging = false)} />
{/if}

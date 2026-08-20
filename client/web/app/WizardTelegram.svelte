<script>
  // Шаг мастера: учётная запись Telegram.
  //
  // Поля здесь голые, без коробки раздела: их три, и рамка с шапкой обещала бы
  // соседей, которых на шаге нет.
  //
  // Сам вход — код и облачный пароль — живёт в окне поверх шага: заводить для
  // мастера второй значило бы держать два входа в один Telegram.
  import WizardFoot from '$components/WizardFoot.svelte';
  import WizardStatus from '$components/WizardStatus.svelte';

  import { living } from '$state/alive.js';
  import { loginTrouble } from '$state/settings.js';

  import TelegramLogin from './TelegramLogin.svelte';

  let { ask, say, onback, onnext } = $props();

  let draft = $state({ api_id: '', api_hash: '', phone: '' });
  let status = $state(null);
  let logging = $state(false);

  const alive = living();

  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive.now) return;
    if (!draft.api_id) {
      draft = { api_id: now.tg.api_id, api_hash: now.tg.api_hash, phone: now.tg.phone };
    }
  }

  /** Запросить код в Telegram.
   *
   * Пробелы срезаются здесь, а не при наборе: ключ приезжает вставкой из чужого
   * окна вместе с пробелом на конце, и уехать на мост должен уже обрезанным.
   */
  function sendCode() {
    draft = {
      api_id: draft.api_id.trim(),
      api_hash: draft.api_hash.trim(),
      phone: draft.phone.trim(),
    };
    if (loginTrouble(draft)) {
      status = { tone: 'err', text: 'Заполните все поля.' };
      return;
    }
    status = { tone: 'busy', text: 'Запрашиваем код в Telegram...' };
    logging = true;
  }

  /** Вход удался: шаг сделан, дальше ведёт он сам.
   *
   * Отдельной кнопки «Дальше» на шаге нет: после входа человеку здесь делать
   * нечего, и ждать от него ещё одного нажатия не за чем.
   */
  function loggedIn() {
    logging = false;
    status = null;
    return onnext();
  }

  function closeLogin() {
    logging = false;
    status = null;
  }

  $effect(() => {
    const settled = alive.mounted();
    refresh();
    return () => {
      settled();
    };
  });
</script>

<div class="wiz-body">
  <div class="wiz-title">Telegram-аккаунт</div>
  <div class="wiz-subtitle">
    Бот заходит в Telegram как обычный клиент. Для этого нужны <strong>api_id</strong> и
    <strong>api_hash</strong> — пара идентификатор/ключ, которую Telegram выдаёт каждому
    приложению.
  </div>
  <div class="help">
    <strong>Где их взять:</strong>
    <ol>
      <li>Откройте <code>https://my.telegram.org/auth</code> и войдите по номеру.</li>
      <li>Перейдите в <strong>API development tools</strong>.</li>
      <li>Заполните <strong>App title</strong> и <strong>Short name</strong> — значения любые.</li>
      <li>Скопируйте <strong>App api_id</strong> и <strong>App api_hash</strong> в поля ниже.</li>
    </ol>
  </div>
  <div class="wiz-fields">
    <input class="input mono" maxlength="16" placeholder="api_id" bind:value={draft.api_id} />
    <input class="input mono" maxlength="64" placeholder="api_hash" bind:value={draft.api_hash} />
    <input
      class="input mono"
      maxlength="32"
      placeholder="Телефон в международном формате, например +71234567890"
      bind:value={draft.phone}
    />
    <WizardStatus {status} />
  </div>
</div>

<WizardFoot
  nextLabel="Отправить код"
  nextIcon="send"
  busy={logging}
  {onback}
  onnext={sendCode}
/>

{#if logging}
  <TelegramLogin {say} creds={draft} ondone={loggedIn} onclose={closeLogin} />
{/if}

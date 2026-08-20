<script>
  // Вход в Telegram: три шага и окно поверх экрана настроек.
  //
  // Живёт отдельно от экрана, потому что это своя история с собственным
  // состоянием — шаг, ожидание ответа, отказ — и заканчивается она одним
  // событием наружу: вошли.
  //
  // Зовёт мост напрямую, а не общей обёрткой окна: отказы здесь предметные —
  // неверный код, устаревший код, неверный пароль — и читают их прямо в окне
  // входа. Уйди они в общую плашку, та погасла бы через несколько секунд, а
  // окно осталось бы стоять без объяснения.

  import { call } from '$api/bridge.js';
  import TgLoginDialog from '$components/TgLoginDialog.svelte';
  import { living } from '$state/alive.js';
  import { nextStep } from '$state/settings.js';

  let { say, creds, relogin, ondone, onclose } = $props();

  let step = $state('code');
  let busy = $state(true);
  let error = $state('');

  const alive = living();

  async function stepped(run) {
    busy = true;
    error = '';
    try {
      const answer = await run();
      if (!alive.now) return null;
      busy = false;
      return answer;
    } catch (refusal) {
      if (!alive.now) return null;
      busy = false;
      error = refusal.message;
      return null;
    }
  }

  async function start() {
    const answer = await stepped(() => call('settings.send_code', { ...creds }));
    if (answer !== null) step = nextStep(answer);
  }

  async function submit(value) {
    // Два зова, а не имя за условием: спрятанное в тернарий имя выпадает из
    // шва с мостом, и разъезд с питоном остался бы незамеченным до первого
    // входа с двухфакторной защитой.
    const answer = await stepped(() =>
      step === 'password'
        ? call('settings.confirm_password', { password: value })
        : call('settings.confirm_code', { code: value }),
    );
    if (answer === null) return;
    if (nextStep(answer) === 'done') return ondone();
    step = nextStep(answer);
  }

  async function cancel() {
    onclose();
    // Временный клиент Telegram закрывается на той стороне: иначе остаётся
    // открытый сокет, а следующая попытка упирается в «код уже отправлен».
    try {
      await call('settings.cancel_login');
    } catch (refusal) {
      // Окно уже закрыто, и показать отказ в нём негде — он уходит общей
      // плашкой. Промолчать нельзя: незакрытый вход виден только на следующей
      // попытке, и объяснить её тогда будет нечем.
      say(`Вход не закрылся: ${refusal.message}`, true);
    }
  }

  $effect(() => {
    const settled = alive.mounted();
    start();
    return () => {
      settled();
    };
  });
</script>

<!-- Окно пересоздаётся на смене шага: код и облачный пароль — разные секреты,
     и набранный код не должен доехать до поля пароля. -->
{#key step}
  <TgLoginDialog
    {step}
    phone={creds.phone}
    {relogin}
    {busy}
    {error}
    onsubmit={submit}
    oncancel={cancel}
  />
{/key}

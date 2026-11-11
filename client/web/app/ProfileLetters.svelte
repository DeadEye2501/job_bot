<script>
  // Вкладка «Letters»: сопроводительные письма профиля — полное и короткое, по-
  // русски над чертой и по-английски под ней.
  //
  // Записывается по ходу, как анкета: набранное уезжает, когда человек
  // остановился, ушёл из поля или попросил записать с клавиатуры. Мост
  // принимает все четыре письма разом, поэтому уезжают они вместе.

  import DelayedTextarea from '$components/DelayedTextarea.svelte';
  import { living } from '$state/alive.js';
  import { autosave } from '$state/autosave.js';
  import { oneWrite } from '$state/one_write.js';
  import { TYPING_DELAY } from '$state/profile.js';

  const FULL_MAX = 4000;

  // Пары по языкам: между ними встаёт черта. Предел короткого приходит с моста:
  // длиннее подписи Telegram отклик молча взял бы письмо модели, и держит его
  // само поле.
  const GROUPS = [
    [
      { key: 'ru', placeholder: 'Полное сопроводительное письмо' },
      { key: 'ru_short', placeholder: 'Короткое сопроводительное письмо', short: true },
    ],
    [
      { key: 'en', placeholder: 'Full cover letter' },
      { key: 'en_short', placeholder: 'Short cover letter', short: true },
    ],
  ];

  let { ask } = $props();

  let form = $state(null);
  let shortMax = $state(null);

  const alive = living();

  const write = oneWrite(async (sending) => (await ask('profile.save_letters', sending)) !== null);

  const saver = autosave({ delay: TYPING_DELAY, save: () => write({ ...form }) });

  async function refresh() {
    const now = await ask('profile.letters');
    if (now === null || !alive.now) return;
    shortMax = now.short_max;
    form = Object.fromEntries(Object.entries(now.letters).map(([key, text]) => [key, text ?? '']));
    saver.known(JSON.stringify(form));
  }

  /** Набранное в поле: в письма ложится сразу, на мост уедет по остановке.
   *  Обрезка здесь — как в анкете: пробел на краю правкой не считается. */
  function typed(key, value) {
    form = { ...form, [key]: value.trim() };
    saver.typed(JSON.stringify(form));
  }

  $effect(() => {
    return alive.entered(refresh);
  });
</script>

{#if form === null}
  <div class="placeholder-content">Загрузка…</div>
{:else}
  <div class="page-head">
    <div class="page-title">Профиль / Letters</div>
  </div>

  <div class="form-grid letters">
    {#each GROUPS as group, at (at)}
      {#if at > 0}<div class="letters-split span-2"></div>{/if}
      {#each group as one (one.key)}
        <DelayedTextarea
          maxlength={one.short ? shortMax : FULL_MAX}
          placeholder={one.placeholder}
          lines={10}
          value={form[one.key]}
          ontyped={(text) => typed(one.key, text)}
          onflush={() => saver.flush()}
        />
      {/each}
    {/each}
  </div>
{/if}

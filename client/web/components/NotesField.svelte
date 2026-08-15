<script>
  // Заметка с отложенной записью: набранное уезжает, когда человек остановился,
  // а легшее в базу отзывается вспышкой рамки.
  //
  // Своим компонентом: так набирают три заметки — о вакансии, о человеке и о
  // компании, — и правила у них одни. Записанное приходит ответом от того, кто
  // писал: мост сводит пробельную заметку к пустоте, и не прими мы его ответ,
  // следующая же пауза послала бы тот же вопрос заново.
  import { autosave } from '$state/autosave.js';
  import { saveKey } from '$state/keys.js';

  // Сколько горит зелёная рамка записанного. Ровно столько же длится её
  // угасание в оформлении: погасшая раньше срока читалась бы как моргание.
  const FLASH_MS = 400;

  let { value, placeholder, delay, limit = null, save } = $props();

  let text = $state(value ?? '');
  let flashed = $state(false);
  let flashTimer = null;

  const saver = autosave({ delay, save: (typed) => write(typed) });

  async function write(typed) {
    const stored = await save(typed);
    if (stored === null) return;
    saver.known(stored);
    flashed = true;
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => (flashed = false), FLASH_MS);
  }

  // Пришедшее с моста ложится в «что лежит в базе», но не в само поле: карточку
  // перечитывают и по чужой вести, и пришедшее посреди набора стёрло бы
  // набранное. Поле принимает значение один раз — при заведении.
  $effect(() => {
    saver.known(value ?? '');
  });

  $effect(() => () => {
    // Набранное и не уехавшее отправляем на прощание: поле закрывают вместе с
    // карточкой, и ждать паузы больше нечему.
    saver.flush();
    clearTimeout(flashTimer);
  });
</script>

<textarea
  class="notes-area"
  class:saved-flash={flashed}
  maxlength={limit}
  {placeholder}
  bind:value={text}
  oninput={() => saver.typed(text)}
  onblur={() => saver.flush()}
  onkeydown={(event) => saveKey(event) && saver.flush()}
></textarea>

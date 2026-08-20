<script>
  // Заметка с отложенной записью: набранное уезжает, когда человек остановился,
  // а легшее в базу отзывается вспышкой рамки.
  //
  // Своим компонентом: так набирают три заметки — о вакансии, о человеке и о
  // компании, — и правила у них одни. Записанное приходит ответом от того, кто
  // писал: мост сводит пробельную заметку к пустоте, и не прими мы его ответ,
  // следующая же пауза послала бы тот же вопрос заново.
  import { untrack } from 'svelte';

  import { autosave } from '$state/autosave.js';
  import { flashing } from '$state/flash.js';
  import { saveKey } from '$state/keys.js';

  // Предел длины заметки — один на все три её места. В базе длина не
  // ограничена вовсе, и разъедься числа по карточкам, человек набирал бы у
  // компании столько, сколько у вакансии уже не помещается. Про соседние поля
  // — пояснение в ленте, поля форм — предел этот ничего не говорит: у них свои
  // предметы и свои числа.
  const LIMIT = 2000;

  let { value, placeholder, delay, owner, save } = $props();

  // Номер записи запечатан при заведении поля, а не читается на отправке.
  // Отправок две, и вторая — прощальная: она случается уже после того, как
  // карточка сменила запись. Читай мы номер тогда, набранное для прежней
  // записи уехало бы к соседней и затёрло её заметку, а сама прежняя осталась
  // бы ни с чем. Поле заводится заново на каждую запись — тем и держится.
  const owned = untrack(() => owner);

  let text = $state(untrack(() => value ?? ''));
  let flashed = $state(false);

  const mark = flashing((on) => (flashed = on));
  const saver = autosave({ delay: untrack(() => delay), save: (typed) => write(typed) });

  async function write(typed) {
    const stored = await save(owned, typed);
    if (stored === null) return false;
    saver.known(stored);
    mark();
    return true;
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
  });
</script>

<textarea
  class="textarea notes-area"
  class:saved-flash={flashed}
  maxlength={LIMIT}
  {placeholder}
  bind:value={text}
  oninput={() => saver.typed(text)}
  onblur={() => saver.flush()}
  onkeydown={(event) => saveKey(event) && saver.flush()}
></textarea>

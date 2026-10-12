<script>
  import { modeChosen, modeHintAt } from '$state/modes.js';

  let { mode, disabled, title, onpick } = $props();
  // Что включит нажатие там, где сейчас курсор. Запертый говорит своё — почему
  // заперт, — и это сильнее.
  let hint = $state('');

  /** Место события на дорожке и её ширина — для нажатия и для подсказки. */
  function onTrack(event) {
    const box = event.currentTarget.querySelector('.mode-track').getBoundingClientRect();
    return { offsetX: event.clientX - box.left, width: box.width };
  }

  function hover(event) {
    const { offsetX, width } = onTrack(event);
    hint = modeHintAt(offsetX, width);
  }

  function pick(event) {
    // Отказ объясняется словами, а не молчанием: запертую кнопку человек жмёт
    // именно затем, чтобы узнать, почему она заперта.
    if (disabled) return onpick(null);
    // Мерить дорожку умеет только разметка, а решать по померенному — правило
    // в состоянии: сюда уезжают место, ширина и `detail`, обратно — режим.
    const chosen = modeChosen({ detail: event.detail, ...onTrack(event) }, mode);
    // Пустое — нажатие мимо дорожки. Тот же режим не отправляем тоже: мост
    // ответил бы тем же значением, а лишний зов разбудил бы бота ни за чем.
    if (chosen && chosen !== mode) onpick(chosen);
  }
</script>

<button
  class="mode-control"
  class:is-disabled={disabled}
  data-mode={mode}
  title={title || hint}
  aria-disabled={disabled}
  onclick={pick}
  onmousemove={hover}
>
  <span class="mode-track"><span class="mode-knob"></span></span>
</button>

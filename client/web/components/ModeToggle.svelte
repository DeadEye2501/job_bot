<script>
  import { modeAt, nextMode } from '$state/modes.js';

  let { mode, disabled, title, onpick } = $props();

  function pick(event) {
    // Отказ объясняется словами, а не молчанием: запертую кнопку человек жмёт
    // именно затем, чтобы узнать, почему она заперта.
    if (disabled) return onpick(null);
    // Нажатие с клавиатуры места не имеет — `detail` у него равен нулю, — и
    // выбирать по месту там нечего: идём по кругу. Без этого отступ выходил
    // отрицательным, и с клавиатуры был доступен один «Off».
    if (event.detail === 0) return onpick(nextMode(mode));
    const track = event.currentTarget.querySelector('.mode-track');
    const box = track.getBoundingClientRect();
    const chosen = modeAt(event.clientX - box.left, box.width);
    // Пустое — нажатие мимо дорожки, по слову режима: оно подпись, а не орган
    // управления. Тот же режим не отправляем тоже: мост ответил бы тем же
    // значением, а лишний зов разбудил бы бота ни за чем.
    if (chosen && chosen !== mode) onpick(chosen);
  }
</script>

<button
  class="mode-control"
  class:is-disabled={disabled}
  data-mode={mode}
  {title}
  aria-disabled={disabled}
  onclick={pick}
>
  <span class="mode-text">{mode}</span>
  <span class="mode-track"><span class="mode-knob"></span></span>
</button>

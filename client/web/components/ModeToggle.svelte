<script>
  import { modeAt } from '$state/modes.js';

  let { mode, disabled, title, onpick } = $props();

  function pick(event) {
    // Отказ объясняется словами, а не молчанием: запертую кнопку человек жмёт
    // именно затем, чтобы узнать, почему она заперта.
    if (disabled) return onpick(null);
    const track = event.currentTarget.querySelector('.mode-track');
    const box = track.getBoundingClientRect();
    const chosen = modeAt(event.clientX - box.left, box.width);
    // Тот же режим не отправляем: мост ответил бы тем же значением, а лишний
    // зов разбудил бы бота ни за чем.
    if (chosen !== mode) onpick(chosen);
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

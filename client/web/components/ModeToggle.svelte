<script>
  import { modeChosen } from '$state/modes.js';

  let { mode, onpick } = $props();

  function pick(event) {
    // Мерить дорожку умеет только разметка, а решать по померенному — правило
    // в состоянии: сюда уезжают место, ширина и `detail`, обратно — режим.
    const box = event.currentTarget.querySelector('.mode-track').getBoundingClientRect();
    const chosen = modeChosen(
      { detail: event.detail, offsetX: event.clientX - box.left, width: box.width },
      mode,
    );
    // Пустое — нажатие мимо дорожки, по слову режима: оно подпись, а не орган
    // управления. Тот же режим не отправляем тоже: мост ответил бы тем же
    // значением, а лишний зов разбудил бы бота ни за чем.
    if (chosen && chosen !== mode) onpick(chosen);
  }
</script>

<button class="mode-control" data-mode={mode} onclick={pick}>
  <span class="mode-text">{mode}</span>
  <span class="mode-track"><span class="mode-knob"></span></span>
</button>

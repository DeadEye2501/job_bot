<script>
  // Рама окна: затемнение, коробка поверх него и клавиатура.
  //
  // Своим компонентом: окон шесть, и начинались они одинаково — то же
  // затемнение, та же коробка, тот же Escape. Нажатие по затемнению закрывало
  // окно у четверых из шести, а у двоих нет: поправка до копий не доехала.
  //
  // `extra` — имя своего вида коробки: ширина у окон разная, и задаёт её каждое
  // само. `over` — имя своего затемнения: место в стопке у окон разное, и вход
  // в Telegram стоит ниже общих окон, но выше экрана настроек. `confirm` просит
  // только подтверждение необратимого: там Enter значит «да», а в окнах с
  // заметкой в несколько строк он обрывал бы набор.
  //
  // `awayCloses` — закрывать ли нажатием по затемнению. Вход в Telegram так не
  // закрывается нарочно: окно спрашивает код, набранный в чужом приложении, и
  // промах мимо коробки стоил бы нового кода.
  import ModalKeys from './ModalKeys.svelte';

  let { extra = '', over = '', confirm = null, awayCloses = true, onclose, children } = $props();

  let box = $state(null);

  $effect(() => {
    // Фокус уходит в окно, если его не взяло поле внутри: оставшись на кнопке,
    // открывшей окно, он отдал бы ей Enter — и окно открылось бы снова.
    if (box && !box.contains(document.activeElement)) box.focus();
  });
</script>

<ModalKeys close={onclose} {confirm} />

<!-- Нажатие по затемнению закрывает окно, нажатие внутри коробки — нет:
     сверяем, что нажали ровно в затемнение, а не всплыло из содержимого. -->
<div
  class="modal-backdrop {over}"
  role="presentation"
  onclick={(event) => awayCloses && event.target === event.currentTarget && onclose()}
>
  <div class="modal-dialog {extra}" role="dialog" aria-modal="true" tabindex="-1" bind:this={box}>
    {@render children()}
  </div>
</div>
